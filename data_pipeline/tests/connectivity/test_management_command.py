"""Tests for the test_source_connectivity management command."""

import json
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from data_pipeline.models import Source, Variable


class TestSourceConnectivityCommandTest(TestCase):
    """Test the test_source_connectivity management command."""

    def setUp(self):
        """Set up test sources."""
        self.test_source = Source.objects.create(
            name="Test Source",
            class_name="TestSource",
            is_active=True,
        )

        self.inactive_source = Source.objects.create(
            name="Inactive Source",
            class_name="TestSource",
            is_active=False,
        )

        # Create test variable
        Variable.objects.create(
            source=self.test_source,
            code="test_var",
            name="Test Variable",
            period="day",
            adm_level=1,
            type="quantitative",
        )

    def test_command_requires_source_or_all(self):
        """Test that command requires either --source or --all."""
        with self.assertRaises(CommandError) as context:
            call_command("test_source_connectivity")

        self.assertIn("Must specify either --source or --all", str(context.exception))

    def test_command_source_not_found(self):
        """Test error when specified source not found."""
        with self.assertRaises(CommandError) as context:
            call_command("test_source_connectivity", source="NonExistent")

        self.assertIn("No active source found matching", str(context.exception))

    def test_command_no_active_sources(self):
        """Test warning when no active sources exist."""
        # Deactivate all sources
        Source.objects.all().update(is_active=False)

        out = StringIO()
        call_command("test_source_connectivity", all=True, stdout=out)

        output = out.getvalue()
        self.assertIn("No active sources found to test", output)

    def test_command_specific_source_standard_output(self):
        """Test command with specific source and standard output."""
        out = StringIO()
        call_command("test_source_connectivity", source="Test Source", stdout=out)

        output = out.getvalue()
        self.assertIn("Testing 1 source(s)", output)
        self.assertIn("Test Source", output)
        # TestSource should show partial success (skipped connectivity)
        self.assertTrue("✓" in output or "⚠" in output)

    def test_command_all_sources_summary_output(self):
        """Test command with all sources and summary output."""
        out = StringIO()
        call_command("test_source_connectivity", all=True, summary=True, stdout=out)

        output = out.getvalue()
        self.assertIn("=== Source Connectivity Report ===", output)
        self.assertIn("Test Source", output)
        self.assertIn("Summary:", output)
        # Should not include inactive sources
        self.assertNotIn("Inactive Source", output)

    def test_command_verbose_output(self):
        """Test command with verbose output."""
        out = StringIO()
        call_command("test_source_connectivity", source="Test Source", verbose=True, stdout=out)

        output = out.getvalue()
        self.assertIn("Testing Test Source (TestSource)", output)
        self.assertIn("connectivity:", output)
        self.assertIn("authentication:", output)

    def test_command_json_output(self):
        """Test command with JSON output."""
        out = StringIO()
        call_command("test_source_connectivity", source="Test Source", json=True, stdout=out)

        output = out.getvalue()

        # Should be valid JSON
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            self.fail("Output is not valid JSON")

        # Check JSON structure
        self.assertIn("test_run_timestamp", data)
        self.assertIn("total_sources", data)
        self.assertIn("results", data)
        self.assertEqual(data["total_sources"], 1)
        self.assertEqual(len(data["results"]), 1)

        # Check result structure
        result = data["results"][0]
        self.assertEqual(result["source_name"], "Test Source")
        self.assertIn("overall_status", result)
        self.assertIn("test_timestamp", result)

    @patch("data_pipeline.sources.testsource.TestSource.run_all_connectivity_tests")
    def test_command_handles_source_exceptions(self, mock_run_tests):
        """Test that command handles exceptions from source tests."""
        # Mock an exception during testing
        mock_run_tests.side_effect = Exception("Test error")

        out = StringIO()
        err = StringIO()

        # Command should not crash, but should exit with error code
        with self.assertRaises(SystemExit) as context:
            call_command("test_source_connectivity", source="Test Source", stdout=out, stderr=err)

        # Should exit with error code 1
        self.assertEqual(context.exception.code, 1)

    @patch("data_pipeline.sources.testsource.TestSource.run_all_connectivity_tests")
    def test_command_fail_fast_option(self, mock_run_tests):
        """Test --fail-fast option exits on first failure."""
        # Mock a failed test
        mock_run_tests.return_value = {
            "source_name": "Test Source",
            "overall_status": "failed",
            "test_timestamp": "2025-01-01T00:00:00",
            "tests": {
                "connectivity": {"status": "failed", "error": "Connection failed"}
            },
            "summary": "Connection failed"
        }

        out = StringIO()
        err = StringIO()

        with self.assertRaises(SystemExit) as context:
            call_command("test_source_connectivity", source="Test Source", fail_fast=True, stdout=out, stderr=err)

        self.assertEqual(context.exception.code, 1)
        output = out.getvalue()
        self.assertIn("exiting due to --fail-fast", output)

    def test_command_partial_matching(self):
        """Test that source matching works with partial names."""
        # Create source with longer name
        longer_source = Source.objects.create(
            name="IDMC GIDD - Global Internal Displacement Database",
            class_name="TestSource",
            is_active=True,
        )

        Variable.objects.create(
            source=longer_source,
            code="test_var2",
            name="Test Variable 2",
            period="day",
            adm_level=1,
            type="quantitative",
        )

        out = StringIO()
        call_command("test_source_connectivity", source="IDMC", stdout=out)

        output = out.getvalue()
        self.assertIn("IDMC GIDD", output)

    def test_command_exit_code_on_failures(self):
        """Test that command exits with error code when sources fail."""
        # Create a source that will fail (invalid class name)
        failing_source = Source.objects.create(
            name="Failing Source",
            class_name="NonExistentSource",  # This will fail to import
            is_active=True,
        )

        out = StringIO()
        err = StringIO()

        with self.assertRaises(SystemExit) as context:
            call_command("test_source_connectivity", source="Failing", stdout=out, stderr=err)

        # Should exit with error code 1 due to failures
        self.assertEqual(context.exception.code, 1)

    def test_command_success_exit_code(self):
        """Test that command exits with code 0 when all tests pass."""
        out = StringIO()

        # This should succeed (TestSource with variables should work)
        try:
            call_command("test_source_connectivity", source="Test Source", stdout=out)
            # If we reach here, command succeeded (didn't call sys.exit)
        except SystemExit as e:
            if e.code != 0:
                self.fail(f"Command exited with non-zero code: {e.code}")

    @patch("data_pipeline.management.commands.test_source_connectivity.Command._get_source_class")
    def test_command_import_error_handling(self, mock_get_class):
        """Test handling of source class import errors."""
        mock_get_class.side_effect = CommandError("Could not import source class")

        with self.assertRaises(CommandError) as context:
            call_command("test_source_connectivity", source="Test Source")

        self.assertIn("Could not import source class", str(context.exception))

    def test_command_multiple_sources_matching(self):
        """Test command behavior when multiple sources match pattern."""
        # Create additional source matching pattern
        Source.objects.create(
            name="Test Source 2",
            class_name="TestSource",
            is_active=True,
        )

        out = StringIO()
        call_command("test_source_connectivity", source="Test", stdout=out)

        output = out.getvalue()
        # Should test both matching sources
        self.assertIn("Testing 2 source(s)", output)


class CommandOutputFormattingTest(TestCase):
    """Test different output formatting options."""

    def setUp(self):
        """Set up test source with predictable behavior."""
        self.source = Source.objects.create(
            name="Predictable Source",
            class_name="TestSource",
            is_active=True,
        )

        Variable.objects.create(
            source=self.source,
            code="test_var",
            name="Test Variable",
            period="day",
            adm_level=1,
            type="quantitative",
        )

    def test_standard_output_format(self):
        """Test standard output format structure."""
        out = StringIO()
        call_command("test_source_connectivity", source="Predictable", stdout=out)

        output = out.getvalue()
        lines = [line.strip() for line in output.split("\n") if line.strip()]

        # Should have testing message, blank line, result, blank line
        self.assertTrue(any("Testing" in line for line in lines))
        self.assertTrue(any("Predictable Source" in line for line in lines))

    def test_summary_output_symbols(self):
        """Test that summary output uses correct symbols."""
        out = StringIO()
        call_command("test_source_connectivity", source="Predictable", summary=True, stdout=out)

        output = out.getvalue()
        # Should contain one of the status symbols
        self.assertTrue(any(symbol in output for symbol in ["✓", "✗", "⚠"]))

    def test_json_output_structure(self):
        """Test JSON output has correct structure."""
        out = StringIO()
        call_command("test_source_connectivity", source="Predictable", json=True, stdout=out)

        data = json.loads(out.getvalue())

        # Verify top-level structure
        required_keys = ["test_run_timestamp", "total_sources", "results"]
        for key in required_keys:
            self.assertIn(key, data)

        # Verify results structure
        self.assertEqual(len(data["results"]), 1)
        result = data["results"][0]

        required_result_keys = ["source_name", "overall_status", "test_timestamp"]
        for key in required_result_keys:
            self.assertIn(key, result)
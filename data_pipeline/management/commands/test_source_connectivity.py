"""Management command to test individual data source connectivity and authentication."""

import json
import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from data_pipeline.models import Source


class Command(BaseCommand):
    """Test individual data source connectivity, authentication, and basic data retrieval."""

    help = "Test data source connectivity, authentication, and basic data retrieval"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--source",
            type=str,
            help="Test specific source by name (e.g., 'IDMC GIDD', 'ACLED')"
        )

        parser.add_argument(
            "--all",
            action="store_true",
            help="Test all active sources"
        )

        parser.add_argument(
            "--json",
            action="store_true",
            help="Output results in JSON format"
        )

        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed output"
        )

        parser.add_argument(
            "--summary",
            action="store_true",
            help="Show summary report format"
        )

        parser.add_argument(
            "--fail-fast",
            action="store_true",
            help="Exit on first failure (useful for CI/CD)"
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        if not options["source"] and not options["all"]:
            raise CommandError("Must specify either --source or --all")

        # Get sources to test
        if options["source"]:
            sources = Source.objects.filter(name__icontains=options["source"], is_active=True)
            if not sources.exists():
                raise CommandError(f"No active source found matching '{options['source']}'")
        else:
            sources = Source.objects.filter(is_active=True)

        if not sources.exists():
            self.stdout.write(self.style.WARNING("No active sources found to test"))
            return

        # Run tests
        results = []
        failed_sources = []

        for source in sources:
            try:
                result = self._test_source(source, options)
                results.append(result)

                if result["overall_status"] == "failed":
                    failed_sources.append(source.name)
                    if options["fail_fast"]:
                        self.stdout.write(
                            self.style.ERROR(f"✗ {source.name}: Test failed - exiting due to --fail-fast")
                        )
                        sys.exit(1)

            except Exception as e:
                error_result = {
                    "source_name": source.name,
                    "overall_status": "error",
                    "error": str(e),
                    "test_timestamp": timezone.now().isoformat()
                }
                results.append(error_result)
                failed_sources.append(source.name)

                if options["fail_fast"]:
                    self.stdout.write(
                        self.style.ERROR(f"✗ {source.name}: Error - {str(e)} - exiting due to --fail-fast")
                    )
                    sys.exit(1)

        # Output results
        if options["json"]:
            self._output_json(results)
        elif options["summary"]:
            self._output_summary(results, failed_sources)
        else:
            self._output_standard(results, options["verbose"])

        # Exit with error code if any sources failed
        if failed_sources:
            sys.exit(1)

    def _test_source(self, source: Source, options: dict) -> dict[str, Any]:
        """Test a single source and return results."""
        try:
            # Import and instantiate the source class
            source_class = self._get_source_class(source)
            source_instance = source_class(source)

            if options["verbose"]:
                self.stdout.write(f"Testing {source.name} ({source.class_name})...")

            # Run all connectivity tests
            results = source_instance.run_all_connectivity_tests()
            return results

        except Exception as e:
            return {
                "source_name": source.name,
                "overall_status": "error",
                "error": f"Failed to instantiate source: {str(e)}",
                "test_timestamp": timezone.now().isoformat()
            }

    def _get_source_class(self, source: Source):
        """Get the source class by importing it dynamically."""
        try:
            module_name = f"data_pipeline.sources.{source.class_name.lower()}"
            module = __import__(module_name, fromlist=[source.class_name])
            return getattr(module, source.class_name)
        except (ImportError, AttributeError) as e:
            raise CommandError(f"Could not import source class {source.class_name}: {e}")

    def _output_json(self, results: list):
        """Output results in JSON format."""
        output = {
            "test_run_timestamp": timezone.now().isoformat(),
            "total_sources": len(results),
            "results": results
        }
        self.stdout.write(json.dumps(output, indent=2))

    def _output_summary(self, results: list, failed_sources: list):
        """Output results in summary format."""
        self.stdout.write("=== Source Connectivity Report ===")

        for result in results:
            name = result["source_name"]
            status = result["overall_status"]

            if status == "success":
                symbol = "✓"
                style = self.style.SUCCESS
            elif status == "partial":
                symbol = "⚠"
                style = self.style.WARNING
            else:
                symbol = "✗"
                style = self.style.ERROR

            summary = result.get("summary", "No summary available")
            self.stdout.write(style(f"{symbol} {name}: {summary}"))

        self.stdout.write("")
        successful = len(results) - len(failed_sources)
        warnings = len([r for r in results if r["overall_status"] == "partial"])

        summary_line = f"Summary: {successful}/{len(results)} sources operational"
        if len(failed_sources) > 0:
            summary_line += f", {len(failed_sources)} failed"
        if warnings > 0:
            summary_line += f", {warnings} warnings"

        self.stdout.write(summary_line)

    def _output_standard(self, results: list, verbose: bool):
        """Output results in standard format."""
        self.stdout.write(f"Testing {len(results)} source(s)...")
        self.stdout.write("")

        for result in results:
            name = result["source_name"]
            status = result["overall_status"]

            if status == "success":
                self.stdout.write(self.style.SUCCESS(f"✓ {name}"))
            elif status == "partial":
                self.stdout.write(self.style.WARNING(f"⚠ {name}"))
            else:
                self.stdout.write(self.style.ERROR(f"✗ {name}"))

            if verbose:
                self._output_verbose_details(result)
            elif status != "success":
                # Show brief error info for failed tests
                if "error" in result:
                    self.stdout.write(f"  Error: {result['error']}")
                else:
                    summary = result.get("summary", "No details available")
                    self.stdout.write(f"  {summary}")

        self.stdout.write("")

    def _output_verbose_details(self, result: dict):
        """Output verbose details for a single source test."""
        tests = result.get("tests", {})

        for test_name, test_result in tests.items():
            status = test_result["status"]

            if status == "success":
                symbol = "  ✓"
                style = self.style.SUCCESS
            elif status == "skipped":
                symbol = "  -"
                style = self.style.WARNING
            else:
                symbol = "  ✗"
                style = self.style.ERROR

            self.stdout.write(style(f"{symbol} {test_name}: {status}"))

            if status == "failed" and "error" in test_result:
                self.stdout.write(f"    Error: {test_result['error']}")
            elif status == "success":
                # Show some success details
                if test_name == "connectivity" and "response_time_ms" in test_result:
                    self.stdout.write(f"    Response time: {test_result['response_time_ms']}ms")
                elif test_name == "authentication" and "configured_vars" in test_result:
                    vars_str = ", ".join(test_result["configured_vars"])
                    self.stdout.write(f"    Configured: {vars_str}")
                elif test_name == "data_retrieval" and "variable_tested" in test_result:
                    self.stdout.write(f"    Tested variable: {test_result['variable_tested']}")
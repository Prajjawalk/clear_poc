"""Integration tests for source connectivity testing functionality."""

import os
from unittest.mock import Mock, patch

from django.test import TestCase

from data_pipeline.models import Source, Variable
from data_pipeline.sources.acled import ACLED
from data_pipeline.sources.dataminr import Dataminr
from data_pipeline.sources.idmcgidd import IDMCGIDD
from data_pipeline.sources.iom import IOM
from data_pipeline.sources.reliefweb import ReliefWeb
from data_pipeline.sources.testsource import TestSource


class SourceConnectivityTestCase(TestCase):
    """Test source connectivity testing methods."""

    def setUp(self):
        """Set up test sources and variables."""
        self.idmc_source = Source.objects.create(
            name="IDMC GIDD - Test",
            class_name="IDMCGIDD",
            base_url="https://helix-tools-api.idmcdb.org",
            is_active=True,
        )

        self.acled_source = Source.objects.create(
            name="ACLED - Test",
            class_name="ACLED",
            base_url="https://acleddata.com",
            is_active=True,
        )

        self.reliefweb_source = Source.objects.create(
            name="ReliefWeb - Test",
            class_name="ReliefWeb",
            base_url="https://api.reliefweb.int/v2",
            is_active=True,
        )

        self.testsource = Source.objects.create(
            name="Test Source",
            class_name="TestSource",
            base_url="",  # TestSource has no base_url
            is_active=True,
        )

        # Create test variables
        Variable.objects.create(
            source=self.idmc_source,
            code="test_idmc_var",
            name="Test IDMC Variable",
            period="year",
            adm_level=1,
            type="quantitative",
        )

        Variable.objects.create(
            source=self.acled_source,
            code="test_acled_var",
            name="Test ACLED Variable",
            period="event",
            adm_level=2,
            type="quantitative",
        )

        Variable.objects.create(
            source=self.testsource,
            code="test_var",
            name="Test Variable",
            period="day",
            adm_level=1,
            type="quantitative",
        )

    def test_base_class_required_env_vars_default(self):
        """Test that base class returns empty list for required env vars."""
        source = TestSource(self.testsource)
        required_vars = source.get_required_env_vars()
        self.assertEqual(required_vars, [])

    def test_source_specific_required_env_vars(self):
        """Test that sources specify their required environment variables."""
        # IDMC GIDD
        idmc = IDMCGIDD(self.idmc_source)
        self.assertEqual(idmc.get_required_env_vars(), ["IDMC_API_KEY"])

        # ACLED
        acled = ACLED(self.acled_source)
        self.assertEqual(acled.get_required_env_vars(), ["ACLED_USERNAME", "ACLED_API_KEY"])

        # ReliefWeb
        reliefweb = ReliefWeb(self.reliefweb_source)
        self.assertEqual(reliefweb.get_required_env_vars(), [])

    def test_source_specific_test_parameters(self):
        """Test that sources provide appropriate test parameters."""
        # IDMC GIDD
        idmc = IDMCGIDD(self.idmc_source)
        params = idmc.get_test_parameters()
        self.assertEqual(params["year"], 2023)
        self.assertIn("iso3__in", params)

        # ACLED
        acled = ACLED(self.acled_source)
        params = acled.get_test_parameters()
        self.assertEqual(params["start_date"], "2025-09-18")
        self.assertEqual(params["end_date"], "2025-09-18")

        # ReliefWeb
        reliefweb = ReliefWeb(self.reliefweb_source)
        params = reliefweb.get_test_parameters()
        self.assertEqual(params["disaster_id"], "52407")

    def test_connectivity_test_no_base_url(self):
        """Test connectivity test when source has no base_url."""
        source = TestSource(self.testsource)
        result = source.test_connectivity()

        self.assertEqual(result["status"], "skipped")
        self.assertIn("No base_url configured", result["reason"])

    @patch("requests.get")
    def test_connectivity_test_success(self, mock_get):
        """Test successful connectivity test."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.elapsed.total_seconds.return_value = 0.25
        mock_get.return_value = mock_response

        source = ReliefWeb(self.reliefweb_source)
        result = source.test_connectivity()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["status_code"], 200)
        self.assertIn("response_time_ms", result)
        self.assertIn("url_tested", result)

    @patch("requests.get")
    def test_connectivity_test_failure(self, mock_get):
        """Test failed connectivity test."""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.elapsed.total_seconds.return_value = 0.1
        mock_get.return_value = mock_response

        source = ReliefWeb(self.reliefweb_source)
        result = source.test_connectivity()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["status_code"], 500)

    @patch("requests.get")
    def test_connectivity_test_exception(self, mock_get):
        """Test connectivity test when request raises exception."""
        # Mock request exception
        mock_get.side_effect = Exception("Connection timeout")

        source = ReliefWeb(self.reliefweb_source)
        result = source.test_connectivity()

        self.assertEqual(result["status"], "failed")
        self.assertIn("Connection timeout", result["error"])

    def test_authentication_test_no_credentials_required(self):
        """Test authentication test for source with no credentials."""
        source = ReliefWeb(self.reliefweb_source)
        result = source.test_authentication()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["credentials_required"], False)
        self.assertIn("No credentials required", result["message"])

    @patch.dict(os.environ, {}, clear=True)
    def test_authentication_test_missing_credentials(self):
        """Test authentication test with missing credentials."""
        source = IDMCGIDD(self.idmc_source)
        result = source.test_authentication()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["credentials_required"], True)
        self.assertIn("IDMC_API_KEY", result["missing_vars"])
        self.assertIn("Missing environment variables", result["error"])

    @patch.dict(os.environ, {"IDMC_API_KEY": "test_key_123"})
    def test_authentication_test_credentials_present(self):
        """Test authentication test with credentials present."""
        source = IDMCGIDD(self.idmc_source)

        # Call base class test_authentication (not the overridden one)
        result = super(IDMCGIDD, source).test_authentication()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["credentials_required"], True)
        self.assertIn("IDMC_API_KEY", result["configured_vars"])

    def test_data_retrieval_test_no_variables(self):
        """Test data retrieval test when source has no variables."""
        # Create source with no variables
        empty_source = Source.objects.create(
            name="Empty Source",
            class_name="TestSource",
            is_active=True,
        )

        source = TestSource(empty_source)
        result = source.test_data_retrieval()

        self.assertEqual(result["status"], "failed")
        self.assertIn("No variables configured", result["error"])
        self.assertEqual(result["variables_count"], 0)

    @patch.object(TestSource, "get")
    def test_data_retrieval_test_success(self, mock_get):
        """Test successful data retrieval test."""
        mock_get.return_value = True

        source = TestSource(self.testsource)
        result = source.test_data_retrieval()

        self.assertEqual(result["status"], "success")
        self.assertIn("test_parameters", result)

    @patch.object(TestSource, "get")
    def test_data_retrieval_test_failure(self, mock_get):
        """Test failed data retrieval test."""
        mock_get.return_value = False

        source = TestSource(self.testsource)
        result = source.test_data_retrieval()

        self.assertEqual(result["status"], "failed")

    @patch.object(TestSource, "get")
    def test_data_retrieval_test_exception(self, mock_get):
        """Test data retrieval test when get() raises exception."""
        mock_get.side_effect = Exception("API Error")

        source = TestSource(self.testsource)
        result = source.test_data_retrieval()

        self.assertEqual(result["status"], "failed")
        self.assertIn("API Error", result["error"])

    @patch.object(TestSource, "test_connectivity")
    @patch.object(TestSource, "test_authentication")
    @patch.object(TestSource, "test_data_retrieval")
    def test_run_all_connectivity_tests_success(self, mock_retrieval, mock_auth, mock_conn):
        """Test running all connectivity tests successfully."""
        # Mock all tests as successful
        mock_conn.return_value = {"status": "success", "response_time_ms": 100}
        mock_auth.return_value = {"status": "success", "credentials_required": False}
        mock_retrieval.return_value = {"status": "success", "variable_tested": "test_var"}

        source = TestSource(self.testsource)
        results = source.run_all_connectivity_tests()

        self.assertEqual(results["overall_status"], "success")
        self.assertIn("source_name", results)
        self.assertIn("test_timestamp", results)
        self.assertIn("tests", results)
        self.assertIn("summary", results)

        # Check individual test results
        self.assertEqual(results["tests"]["connectivity"]["status"], "success")
        self.assertEqual(results["tests"]["authentication"]["status"], "success")
        self.assertEqual(results["tests"]["data_retrieval"]["status"], "success")

    @patch.object(TestSource, "test_connectivity")
    @patch.object(TestSource, "test_authentication")
    def test_run_all_connectivity_tests_skip_retrieval(self, mock_auth, mock_conn):
        """Test that data retrieval is skipped when connectivity fails."""
        # Mock connectivity as failed
        mock_conn.return_value = {"status": "failed", "error": "Connection failed"}
        mock_auth.return_value = {"status": "success", "credentials_required": False}

        source = TestSource(self.testsource)
        results = source.run_all_connectivity_tests()

        self.assertEqual(results["overall_status"], "failed")
        self.assertEqual(results["tests"]["connectivity"]["status"], "failed")
        self.assertEqual(results["tests"]["data_retrieval"]["status"], "skipped")
        self.assertIn("Connectivity or authentication failed", results["tests"]["data_retrieval"]["reason"])

    def test_generate_test_summary(self):
        """Test generation of human-readable test summary."""
        source = TestSource(self.testsource)

        # Test successful case
        test_results = {
            "connectivity": {"status": "success", "response_time_ms": 150},
            "authentication": {"status": "success", "credentials_required": True},
            "data_retrieval": {"status": "success"}
        }

        summary = source._generate_test_summary(test_results)
        self.assertIn("API accessible (150ms)", summary)
        self.assertIn("credentials valid", summary)
        self.assertIn("data retrieval OK", summary)

        # Test failed case
        test_results = {
            "connectivity": {"status": "failed"},
            "authentication": {"status": "failed", "missing_vars": ["API_KEY"]},
            "data_retrieval": {"status": "failed"}
        }

        summary = source._generate_test_summary(test_results)
        self.assertIn("API inaccessible", summary)
        self.assertIn("missing: API_KEY", summary)
        self.assertIn("data retrieval failed", summary)

    def test_source_inheritance_pattern(self):
        """Test that sources properly inherit and override base methods."""
        # Test that sources inherit base functionality
        sources = [
            (IDMCGIDD, self.idmc_source),
            (ACLED, self.acled_source),
            (ReliefWeb, self.reliefweb_source),
            (TestSource, self.testsource)
        ]

        for source_class, source_model in sources:
            source = source_class(source_model)

            # All sources should have these base methods
            self.assertTrue(hasattr(source, "test_connectivity"))
            self.assertTrue(hasattr(source, "test_authentication"))
            self.assertTrue(hasattr(source, "test_data_retrieval"))
            self.assertTrue(hasattr(source, "get_required_env_vars"))
            self.assertTrue(hasattr(source, "get_test_parameters"))
            self.assertTrue(hasattr(source, "run_all_connectivity_tests"))

            # Test that overridden methods work
            required_vars = source.get_required_env_vars()
            self.assertIsInstance(required_vars, list)

            test_params = source.get_test_parameters()
            self.assertIsInstance(test_params, dict)


class SourceConnectivityIntegrationTest(TestCase):
    """Integration tests with real source implementations."""

    def setUp(self):
        """Set up real source instances."""
        self.test_source_model = Source.objects.create(
            name="Test Source",
            class_name="TestSource",
            is_active=True,
        )

        # Create a variable for testing
        Variable.objects.create(
            source=self.test_source_model,
            code="test_variable",
            name="Test Variable",
            period="day",
            adm_level=1,
            type="quantitative",
        )

    def test_testsource_full_connectivity_test(self):
        """Test full connectivity test flow with TestSource."""
        source = TestSource(self.test_source_model)
        results = source.run_all_connectivity_tests()

        # TestSource should have partial success (no connectivity due to no base_url)
        self.assertIn(results["overall_status"], ["partial", "success"])
        self.assertEqual(results["tests"]["authentication"]["status"], "success")
        self.assertEqual(results["tests"]["connectivity"]["status"], "skipped")

        # Check that results have expected structure
        self.assertIn("source_name", results)
        self.assertIn("source_class", results)
        self.assertIn("test_timestamp", results)
        self.assertIn("tests", results)
        self.assertIn("summary", results)
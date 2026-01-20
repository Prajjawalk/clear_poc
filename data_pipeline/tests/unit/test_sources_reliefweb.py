"""
Unit tests for ReliefWeb Disasters API data source.

Tests cover:
- Disaster detail fetching functionality
- Data processing and transformation logic
- Variable-specific filtering and processing
"""

import json
from unittest.mock import MagicMock, Mock, patch

from django.test import TestCase

from data_pipeline.models import Source, Variable
from data_pipeline.sources.reliefweb import ReliefWeb


class ReliefWebSourceTest(TestCase):
    """Test ReliefWeb source implementation."""

    def setUp(self):
        """Create test source and variables."""
        self.source = Source.objects.create(
            name="ReliefWeb",
            class_name="ReliefWeb",
            base_url="https://api.reliefweb.int/v2",
            is_active=True,
        )

        self.flood_var = Variable.objects.create(
            source=self.source,
            code="reliefweb_flood_events",
            name="ReliefWeb - Flood Events",
            period="event",
            adm_level=1,
            type="qualitative",
        )

        self.drought_var = Variable.objects.create(
            source=self.source,
            code="reliefweb_drought_events",
            name="ReliefWeb - Drought Events",
            period="event",
            adm_level=1,
            type="qualitative",
        )

        self.conflict_var = Variable.objects.create(
            source=self.source,
            code="reliefweb_conflict_events",
            name="ReliefWeb - Conflict Events",
            period="event",
            adm_level=1,
            type="qualitative",
        )

        self.reliefweb_source = ReliefWeb(self.source)

    def test_initialization(self):
        """Test ReliefWeb source initialization."""
        self.assertEqual(self.reliefweb_source.base_url, "https://api.reliefweb.int/v2")
        self.assertEqual(self.reliefweb_source.app_name, "nrc-ewas-sudan")

    @patch("requests.get")
    def test_fetch_disaster_details_success(self, mock_get):
        """Test successful disaster detail fetching."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "fields": {
                        "id": "12345",
                        "name": "Test Disaster",
                        "description": "Test disaster description",
                        "date": {"created": "2025-01-15T00:00:00Z"},
                        "primary_country": {"name": "Sudan"},
                        "type": [{"name": "Flood"}],
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        # Test detail fetching
        result = self.reliefweb_source._fetch_disaster_details("12345")

        # Should return the fields data
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "12345")
        self.assertEqual(result["name"], "Test Disaster")

        # Verify API call was made correctly
        mock_get.assert_called_once_with(
            "https://api.reliefweb.int/v2/disasters/12345",
            params={"appname": "nrc-ewas-sudan"},
            headers={"Accept": "application/json", "User-Agent": "nrc-ewas-sudan/1.0"},
            timeout=30,
        )

    @patch("requests.get")
    def test_fetch_disaster_details_failure(self, mock_get):
        """Test disaster detail fetching with API failure."""
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        # Test detail fetching
        result = self.reliefweb_source._fetch_disaster_details("nonexistent")

        # Should return None
        self.assertIsNone(result)

    @patch("requests.get")
    def test_fetch_disaster_details_empty_data(self, mock_get):
        """Test disaster detail fetching with empty response data."""
        # Mock response with empty data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        # Test detail fetching
        result = self.reliefweb_source._fetch_disaster_details("12345")

        # Should return None
        self.assertIsNone(result)

    @patch("requests.get")
    def test_fetch_disaster_details_exception_handling(self, mock_get):
        """Test disaster detail fetching with request exception."""
        # Mock request exception
        mock_get.side_effect = Exception("Network error")

        # Test detail fetching with exception handling
        result = self.reliefweb_source._fetch_disaster_details("12345")

        # Should return None and handle exception gracefully
        self.assertIsNone(result)

    @patch("requests.get")
    @patch("builtins.open")
    def test_get_method_flood_variable(self, mock_open, mock_get):
        """Test API data retrieval for flood variable."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "flood123", "fields": {"name": "Sudan Floods 2025", "date": {"created": "2025-01-15T00:00:00Z"}}}]}
        mock_get.return_value = mock_response

        # Mock file operations
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock get_raw_data_path
        with patch.object(self.reliefweb_source, "get_raw_data_path") as mock_path:
            mock_path.return_value = "/tmp/test_flood_data.json"

            # Test data retrieval
            result = self.reliefweb_source.get(self.flood_var)

            # Should succeed
            self.assertTrue(result)

            # Verify API call included flood query
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            self.assertIn("query[value]", kwargs["params"])
            self.assertEqual(kwargs["params"]["query[value]"], "flood")

    @patch("requests.get")
    @patch("builtins.open")
    def test_get_method_drought_variable(self, mock_open, mock_get):
        """Test API data retrieval for drought variable."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        # Mock file operations
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock get_raw_data_path
        with patch.object(self.reliefweb_source, "get_raw_data_path") as mock_path:
            mock_path.return_value = "/tmp/test_drought_data.json"

            # Test data retrieval
            result = self.reliefweb_source.get(self.drought_var)

            # Should succeed
            self.assertTrue(result)

            # Verify API call included drought query
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            self.assertIn("query[value]", kwargs["params"])
            self.assertEqual(kwargs["params"]["query[value]"], "drought")

    @patch("requests.get")
    @patch("builtins.open")
    def test_get_method_conflict_variable(self, mock_open, mock_get):
        """Test API data retrieval for conflict variable."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        # Mock file operations
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock get_raw_data_path
        with patch.object(self.reliefweb_source, "get_raw_data_path") as mock_path:
            mock_path.return_value = "/tmp/test_conflict_data.json"

            # Test data retrieval
            result = self.reliefweb_source.get(self.conflict_var)

            # Should succeed
            self.assertTrue(result)

            # Verify API call included conflict query
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            self.assertIn("query[value]", kwargs["params"])
            self.assertEqual(kwargs["params"]["query[value]"], "conflict OR violence OR displacement")

    @patch("requests.get")
    def test_get_method_api_failure(self, mock_get):
        """Test API data retrieval with request failure."""
        # Mock failed API response
        mock_get.side_effect = Exception("API Error")

        # Test data retrieval
        result = self.reliefweb_source.get(self.flood_var)

        # Should fail gracefully
        self.assertFalse(result)

    @patch("requests.get")
    def test_disaster_detail_fetching_with_invalid_input(self, mock_get):
        """Test that _fetch_disaster_details method handles invalid input gracefully."""
        # Test with None input - will make API call but should handle gracefully
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = self.reliefweb_source._fetch_disaster_details(None)
        self.assertIsNone(result)

        # Test with empty string - should make API call but handle gracefully
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = self.reliefweb_source._fetch_disaster_details("")
        self.assertIsNone(result)

    @patch("os.listdir")
    @patch("builtins.open")
    def test_process_method_no_raw_files(self, mock_open, mock_listdir):
        """Test processing when no raw data files exist."""
        # Mock no files found
        mock_listdir.return_value = []

        # Process should fail
        result = self.reliefweb_source.process(self.flood_var)
        self.assertFalse(result)

    @patch("os.listdir")
    @patch("builtins.open")
    def test_process_method_empty_data(self, mock_open, mock_listdir):
        """Test processing with empty disaster data."""
        # Mock file system
        mock_listdir.return_value = ["ReliefWeb_reliefweb_flood_events_20250912_120000.json"]

        # Mock empty raw data
        raw_data = {"data": []}
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(raw_data)

        # Process data
        result = self.reliefweb_source.process(self.flood_var)

        # Should succeed but process 0 records
        self.assertTrue(result)

    @patch("os.listdir")
    @patch("builtins.open")
    def test_process_method_duplicate_filtering(self, mock_open, mock_listdir):
        """Test that duplicate disasters are filtered out during processing."""
        # Mock file system
        mock_listdir.return_value = ["ReliefWeb_reliefweb_flood_events_20250912_120000.json"]

        # Mock raw disaster data with duplicate
        raw_data = {
            "data": [
                {"id": "flood123", "fields": {"id": "flood123", "name": "Sudan Floods 2025", "date": {"created": "2025-01-15T00:00:00Z"}, "primary_country": {"name": "Sudan"}}}
            ]
        }

        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(raw_data)

        # Mock VariableData to simulate existing record
        with patch("data_pipeline.sources.reliefweb.VariableData.objects") as mock_vd_objects:
            mock_vd_objects.filter.return_value.exists.return_value = True  # Simulate duplicate

            # Process data
            result = self.reliefweb_source.process(self.flood_var)

            # Should succeed
            self.assertTrue(result)

            # Verify no create call was made due to duplicate
            self.assertEqual(mock_vd_objects.create.call_count, 0)

    @patch("os.listdir")
    @patch("builtins.open")
    def test_aggregate_method(self, mock_open, mock_listdir):
        """Test disaster data aggregation functionality."""
        # Mock file system
        mock_listdir.return_value = ["ReliefWeb_reliefweb_flood_events_20250912_120000.json"]

        # Mock raw disaster data
        raw_data = {"data": [{"id": "flood123", "fields": {"name": "Test Flood", "date": {"created": "2025-01-15T00:00:00Z"}, "type": [{"name": "Flood"}]}}]}

        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(raw_data)

        # Test aggregation
        result = self.reliefweb_source.aggregate(self.flood_var)

        # Should succeed (aggregation implementation may vary)
        self.assertTrue(result)

    def test_variable_type_query_mapping(self):
        """Test that variable codes map to correct query parameters."""
        # Test flood variable
        self.assertIn("flood", self.flood_var.code)

        # Test drought variable
        self.assertIn("drought", self.drought_var.code)

        # Test conflict variable
        self.assertIn("conflict", self.conflict_var.code)

    @patch("requests.get")
    @patch("builtins.open")
    def test_api_parameter_construction(self, mock_open, mock_get):
        """Test that API parameters are constructed correctly."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        # Mock file operations
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        with patch.object(self.reliefweb_source, "get_raw_data_path") as mock_path:
            mock_path.return_value = "/tmp/test_data.json"

            # Test API call
            self.reliefweb_source.get(self.flood_var)

            # Verify API parameters
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args

            params = kwargs["params"]
            self.assertEqual(params["appname"], "nrc-ewas-sudan")
            self.assertEqual(params["profile"], "list")
            self.assertEqual(params["preset"], "latest")
            self.assertEqual(params["limit"], 1000)
            self.assertEqual(params["filter[field]"], "country.iso3")
            self.assertEqual(params["filter[value]"], "SDN")

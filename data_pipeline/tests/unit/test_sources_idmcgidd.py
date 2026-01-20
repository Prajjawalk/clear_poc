"""
Unit tests for IDMC GIDD data source.

Tests cover:
- GeoJSON data processing and feature extraction
- Annual displacement data handling by cause (conflict/disaster)
- Compound location parsing (e.g., "North Darfur State, Sudan")
- Location matching with admin level hierarchy
- Data aggregation for duplicate location/date combinations
- Variable-specific data filtering by displacement cause
"""

from datetime import date
from unittest.mock import Mock, patch

from django.test import TestCase

from data_pipeline.models import Source, Variable
from data_pipeline.sources.idmcgidd import IDMCGIDD


class IDMCGIDDSourceTest(TestCase):
    """Test IDMC GIDD source implementation."""

    def setUp(self):
        """Create test source and variables."""
        self.source = Source.objects.create(
            name="IDMC GIDD - Global Internal Displacement Database",
            class_name="IDMCGIDD",
            base_url="https://helix-tools-api.idmcdb.org",
            is_active=True,
        )

        self.conflict_var = Variable.objects.create(
            source=self.source,
            code="idmc_gidd_conflict_displacement",
            name="IDMC GIDD - Conflict Displacement",
            period="year",
            adm_level=1,
            type="quantitative",
        )

        self.disaster_var = Variable.objects.create(
            source=self.source,
            code="idmc_gidd_disaster_displacement",
            name="IDMC GIDD - Disaster Displacement",
            period="year",
            adm_level=1,
            type="quantitative",
        )

        self.total_var = Variable.objects.create(
            source=self.source,
            code="idmc_gidd_total_displacement",
            name="IDMC GIDD - Total Displacement",
            period="year",
            adm_level=1,
            type="quantitative",
        )

        self.gidd_source = IDMCGIDD(self.source)

    def test_compound_location_parsing(self):
        """Test parsing of compound location strings into admin level hierarchy."""
        # Test simple location name
        result = self.gidd_source._parse_compound_location("Al Fasher")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Al Fasher")
        self.assertIsNone(result[0]["level"])

        # Test state, country format
        result = self.gidd_source._parse_compound_location("North Darfur State, Sudan")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "North Darfur State")
        self.assertEqual(result[0]["level"], "1")  # State level
        self.assertEqual(result[1]["name"], "Sudan")
        self.assertEqual(result[1]["level"], "0")  # Country level

        # Test city, country format
        result = self.gidd_source._parse_compound_location("Khartoum, Sudan")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Khartoum")
        self.assertEqual(result[0]["level"], "2")  # Locality/city level
        self.assertEqual(result[1]["name"], "Sudan")
        self.assertEqual(result[1]["level"], "0")

        # Test empty/invalid input
        self.assertEqual(self.gidd_source._parse_compound_location(""), [])
        self.assertEqual(self.gidd_source._parse_compound_location(None), [])

    def test_location_matching_hierarchy(self):
        """Test location matching with admin level hints."""
        mock_location = Mock()
        mock_location.id = 123
        mock_location.name = "North Darfur State"

        location_parts = [{"name": "North Darfur State", "level": "1"}, {"name": "Sudan", "level": "0"}]

        with patch.object(self.gidd_source, "validate_location_match") as mock_match:
            # Mock successful match for first part (state level)
            mock_match.return_value = mock_location

            result_location, result_name, result_level = self.gidd_source._try_match_location_parts(location_parts)

            self.assertEqual(result_location, mock_location)
            self.assertEqual(result_name, "North Darfur State")
            self.assertEqual(result_level, "1")

            # Verify context data was passed with admin level hint
            mock_match.assert_called_once()
            call_args = mock_match.call_args
            self.assertEqual(call_args[0][0], "North Darfur State")  # location name
            self.assertEqual(call_args[1]["context_data"]["expected_admin_level"], "1")

    def test_geojson_feature_processing_by_variable(self):
        """Test processing GeoJSON features for different displacement variables."""
        mock_features = [
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 5000,
                    "Locations name": ["North Darfur State, Sudan"],
                    "Year": 2024,
                    "ISO3": "SDN",
                    "Country": "Sudan",
                    "Locations accuracy": ["Admin 1"],
                }
            },
            {
                "properties": {
                    "Figure cause": "Disaster",
                    "Total figures": 1500,
                    "Locations name": ["Blue Nile State, Sudan"],
                    "Year": 2024,
                    "ISO3": "SDN",
                    "Country": "Sudan",
                    "Locations accuracy": ["Admin 1"],
                }
            },
        ]

        # Test conflict displacement variable - should only process conflict records
        conflict_data = self.gidd_source._process_variable_data(self.conflict_var, mock_features)
        self.assertEqual(len(conflict_data), 1)
        self.assertEqual(conflict_data[0]["value"], 5000.0)
        self.assertEqual(conflict_data[0]["figure_cause"], "conflict")

        # Test disaster displacement variable - should only process disaster records
        disaster_data = self.gidd_source._process_variable_data(self.disaster_var, mock_features)
        self.assertEqual(len(disaster_data), 1)
        self.assertEqual(disaster_data[0]["value"], 1500.0)
        self.assertEqual(disaster_data[0]["figure_cause"], "disaster")

        # Test total displacement variable - should process both conflict and disaster
        total_data = self.gidd_source._process_variable_data(self.total_var, mock_features)
        self.assertEqual(len(total_data), 2)
        values = [dp["value"] for dp in total_data]
        self.assertIn(5000.0, values)
        self.assertIn(1500.0, values)

    def test_annual_date_range_creation(self):
        """Test that annual data creates proper year-based date ranges."""
        mock_features = [
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 2500,
                    "Locations name": ["Khartoum, Sudan"],
                    "Year": 2023,
                    "ISO3": "SDN",
                    "Country": "Sudan",
                }
            }
        ]

        data_points = self.gidd_source._process_variable_data(self.conflict_var, mock_features)

        self.assertEqual(len(data_points), 1)
        data_point = data_points[0]

        # Should create date range for entire year
        self.assertEqual(data_point["start_date"], date(2023, 1, 1))
        self.assertEqual(data_point["end_date"], date(2023, 12, 31))
        self.assertEqual(data_point["period"], "year")

    def test_zero_displacement_filtering(self):
        """Test that records with zero displacement are filtered out."""
        mock_features = [
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 0,  # Should be filtered out
                    "Locations name": ["Location A, Sudan"],
                    "Year": 2024,
                    "ISO3": "SDN",
                }
            },
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 1000,  # Should be included
                    "Locations name": ["Location B, Sudan"],
                    "Year": 2024,
                    "ISO3": "SDN",
                }
            },
        ]

        data_points = self.gidd_source._process_variable_data(self.conflict_var, mock_features)

        # Should only include the record with non-zero displacement
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0]["value"], 1000.0)

    def test_missing_required_fields_handling(self):
        """Test handling of GeoJSON features with missing required fields."""
        mock_features = [
            {
                "properties": {
                    # Missing "Figure cause"
                    "Total figures": 1000,
                    "Locations name": ["Location A, Sudan"],
                    "Year": 2024,
                }
            },
            {
                "properties": {
                    "Figure cause": "Conflict",
                    # Missing "Total figures"
                    "Locations name": ["Location B, Sudan"],
                    "Year": 2024,
                }
            },
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 500,
                    # Missing "Locations name"
                    "Year": 2024,
                }
            },
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 800,
                    "Locations name": ["Location D, Sudan"],
                    # Missing "Year"
                }
            },
            {
                "properties": {
                    # Complete record
                    "Figure cause": "Conflict",
                    "Total figures": 1200,
                    "Locations name": ["Location E, Sudan"],
                    "Year": 2024,
                }
            },
        ]

        data_points = self.gidd_source._process_variable_data(self.conflict_var, mock_features)

        # Should only process the complete record
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0]["value"], 1200.0)

    def test_displacement_data_aggregation(self):
        """Test aggregation of displacement data to prevent duplicate key constraints."""
        # Mock data with same location/date but different records
        data_points = [
            {
                "location_name": "Khartoum",
                "matched_location_object": None,
                "start_date": date(2024, 1, 1),
                "end_date": date(2024, 12, 31),
                "value": 1000.0,
                "figure_cause": "conflict",
                "original_location": "Khartoum, Sudan",
                "text": "Test conflict displacement",
            },
            {
                "location_name": "Khartoum",
                "matched_location_object": None,
                "start_date": date(2024, 1, 1),
                "end_date": date(2024, 12, 31),
                "value": 500.0,
                "figure_cause": "disaster",
                "original_location": "Khartoum, Sudan",
                "text": "Test disaster displacement",
            },
        ]

        aggregated = self.gidd_source._aggregate_displacement_data(data_points, "idmc_gidd_total_displacement")

        # Should aggregate into single record
        self.assertEqual(len(aggregated), 1)

        result = aggregated[0]
        self.assertEqual(result["value"], 1500.0)  # 1000 + 500
        self.assertEqual(sorted(result["aggregated_causes"]), ["conflict", "disaster"])
        self.assertIn("Conflict and Disaster displacement", result["text"])

    def test_text_field_generation(self):
        """Test generation of descriptive text fields."""
        mock_features = [
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 3500,
                    "Locations name": ["West Darfur State, Sudan"],
                    "Year": 2024,
                    "ISO3": "SDN",
                    "Country": "Sudan",
                }
            }
        ]

        data_points = self.gidd_source._process_variable_data(self.conflict_var, mock_features)

        self.assertEqual(len(data_points), 1)
        text = data_points[0]["text"]

        # Text should contain key information
        self.assertIn("3500", str(data_points[0]["value"]))  # Value
        self.assertIn("Conflict", text)  # Displacement cause
        self.assertIn("2024", text)  # Year
        self.assertIn("West Darfur State", text)  # Location
        self.assertIn("IDMC GIDD", text)  # Source identifier

    @patch.dict("os.environ", {"IDMC_API_KEY": "test_key_12345"})
    @patch("requests.get")
    def test_api_key_handling(self, mock_get):
        """Test API key retrieval and usage in requests."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"type": "FeatureCollection", "features": []}
        mock_get.return_value = mock_response

        # Test successful API key retrieval
        api_key = self.gidd_source._get_api_key()
        self.assertEqual(api_key, "test_key_12345")

        # Test API call includes client_id parameter
        result = self.gidd_source.get_all_variables()
        self.assertTrue(result)

        # Verify API was called with correct parameters
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["client_id"], "test_key_12345")
        self.assertIn("iso3__in", params)

    def test_api_key_missing_error(self):
        """Test error handling when API key is not set."""
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as context:
                self.gidd_source._get_api_key()

            self.assertIn("IDMC_API_KEY must be set", str(context.exception))

    def test_date_parameter_handling(self):
        """Test handling of date parameters in API requests."""
        with patch.dict("os.environ", {"IDMC_API_KEY": "test_key"}):
            with patch("requests.get") as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"type": "FeatureCollection", "features": []}
                mock_get.return_value = mock_response

                # Test explicit date parameters
                self.gidd_source.get_all_variables(start_date="2023-01-01", end_date="2023-12-31")

                call_args = mock_get.call_args
                params = call_args[1]["params"]
                self.assertEqual(params["start_date"], "2023-01-01")
                self.assertEqual(params["end_date"], "2023-12-31")

                # Test year parameter
                mock_get.reset_mock()
                self.gidd_source.get_all_variables(year=2023)

                call_args = mock_get.call_args
                params = call_args[1]["params"]
                self.assertEqual(params["year"], 2023)

    def test_incremental_date_parameters(self):
        """Test incremental date parameter determination."""
        with patch.object(self.gidd_source, "get_incremental_date_params") as mock_params:
            with patch.dict("os.environ", {"IDMC_API_KEY": "test_key"}):
                with patch("requests.get") as mock_get:
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"features": []}
                    mock_get.return_value = mock_response

                    # Test incremental data fetch
                    mock_params.return_value = {
                        "incremental": True,
                        "start_date": "2024-06-01",
                        "end_date": "2024-12-31",
                    }

                    self.gidd_source.get_all_variables()

                    call_args = mock_get.call_args
                    params = call_args[1]["params"]
                    self.assertEqual(params["start_date"], "2024-06-01")
                    self.assertEqual(params["end_date"], "2024-12-31")

                    # Test historical data fetch (no existing data)
                    mock_get.reset_mock()
                    mock_params.return_value = {
                        "incremental": False,
                        "start_date": None,
                        "end_date": "2024-12-31",
                    }

                    self.gidd_source.get_all_variables()

                    call_args = mock_get.call_args
                    params = call_args[1]["params"]
                    self.assertEqual(params["start_date"], "2020-01-01")  # Default historical start
                    self.assertEqual(params["end_date"], "2024-12-31")

    def test_invalid_year_handling(self):
        """Test handling of invalid year data in GeoJSON."""
        mock_features = [
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 1000,
                    "Locations name": ["Test Location, Sudan"],
                    "Year": "invalid_year",  # Invalid year
                    "ISO3": "SDN",
                }
            },
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 1500,
                    "Locations name": ["Valid Location, Sudan"],
                    "Year": 2024,  # Valid year
                    "ISO3": "SDN",
                }
            },
        ]

        data_points = self.gidd_source._process_variable_data(self.conflict_var, mock_features)

        # Should only process the record with valid year
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0]["value"], 1500.0)

    def test_location_list_handling(self):
        """Test handling of location name lists in GeoJSON properties."""
        mock_features = [
            {
                "properties": {
                    "Figure cause": "Conflict",
                    "Total figures": 2000,
                    "Locations name": ["Primary Location", "Secondary Location"],  # Multiple locations
                    "Year": 2024,
                    "ISO3": "SDN",
                    "Country": "Sudan",
                }
            }
        ]

        data_points = self.gidd_source._process_variable_data(self.conflict_var, mock_features)

        self.assertEqual(len(data_points), 1)
        # Should use first location name
        self.assertIn("Primary Location", data_points[0]["original_location"])

    def test_location_accuracy_preservation(self):
        """Test that location accuracy information is preserved."""
        mock_features = [
            {
                "properties": {
                    "Figure cause": "Disaster",
                    "Total figures": 800,
                    "Locations name": ["Kassala State, Sudan"],
                    "Year": 2024,
                    "ISO3": "SDN",
                    "Country": "Sudan",
                    "Locations accuracy": ["Admin 1"],
                }
            }
        ]

        data_points = self.gidd_source._process_variable_data(self.disaster_var, mock_features)

        self.assertEqual(len(data_points), 1)
        # Admin level should be preserved from accuracy field
        self.assertEqual(data_points[0]["admin_level"], "Admin 1")

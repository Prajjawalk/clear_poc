"""
Unit tests for IDMC IDU data source.

Tests cover:
- API response parsing and location handling
- Semicolon-separated location splitting into separate data points
- Field mapping correctness (figure, displacement_date, locations_name)
- Data point creation and validation
- Text field population with standard_info_text
"""

from datetime import date

from django.test import TestCase

from data_pipeline.models import Source, Variable
from data_pipeline.sources.idmcidu import IDMCIDU


class IDMCIDUSourceTest(TestCase):
    """Test IDMC IDU source implementation."""

    def setUp(self):
        """Create test source and variables."""
        self.source = Source.objects.create(name="IDMC-IDU - Internal Displacement Updates", class_name="IDMCIDU", base_url="https://helix-tools-api.idmcdb.org", is_active=True)

        self.conflict_var = Variable.objects.create(
            source=self.source, code="idmc_idu_conflict_displacements", name="IDU - Conflict Displacements", period="event", adm_level=1, type="quantitative"
        )

        self.disaster_var = Variable.objects.create(
            source=self.source, code="idmc_idu_disaster_displacements", name="IDU - Disaster Displacements", period="event", adm_level=1, type="quantitative"
        )

        self.idu_source = IDMCIDU(self.source)

    def test_semicolon_separated_locations_create_multiple_data_points(self):
        """Test that semicolon-separated locations are split into separate data points."""
        # Mock API response with semicolon-separated locations
        api_results = [
            {
                "displacement_type": "Conflict",
                "figure": 1000,
                "displacement_date": "2025-01-15",
                "locations_name": "North Darfur State, Sudan; West Darfur State, Sudan; Central Darfur, Sudan",
                "event_name": "Test Multi-Location Event",
                "standard_info_text": "Test: 1,000 displacements, 15 January 2025",
                "iso3": "SDN",
            }
        ]

        data_points = self.idu_source._process_variable_data(self.conflict_var, api_results)

        # Should create 3 separate data points (one per location)
        self.assertEqual(len(data_points), 3)

        # Verify individual locations
        expected_locations = ["North Darfur State, Sudan", "West Darfur State, Sudan", "Central Darfur, Sudan"]

        actual_locations = [dp["location_name"] for dp in data_points]
        self.assertEqual(set(actual_locations), set(expected_locations))

        # All data points should have same value and date
        for dp in data_points:
            self.assertEqual(dp["value"], 1000.0)
            self.assertEqual(dp["start_date"], date(2025, 1, 15))
            self.assertEqual(dp["text"], "Test: 1,000 displacements, 15 January 2025")

    def test_field_mapping_correctness(self):
        """Test that API fields are correctly mapped to data point fields."""
        api_results = [
            {
                "displacement_type": "Disaster",
                "figure": 2500,  # Should map to value
                "displacement_date": "2025-02-10",  # Should map to start_date
                "displacement_end_date": "2025-02-12",  # Should map to end_date
                "locations_name": "Blue Nile State, Sudan",  # Should map to location_name
                "event_name": "Flood Event",
                "standard_info_text": "Sudan: 2,500 displacements (flood), 10-12 February 2025",
                "iso3": "SDN",
            }
        ]

        data_points = self.idu_source._process_variable_data(self.disaster_var, api_results)

        self.assertEqual(len(data_points), 1)
        dp = data_points[0]

        # Verify field mappings
        self.assertEqual(dp["value"], 2500.0)
        self.assertEqual(dp["start_date"], date(2025, 2, 10))
        self.assertEqual(dp["end_date"], date(2025, 2, 12))
        self.assertEqual(dp["location_name"], "Blue Nile State, Sudan")
        self.assertEqual(dp["text"], "Sudan: 2,500 displacements (flood), 10-12 February 2025")

    def test_conflict_vs_disaster_filtering(self):
        """Test that variables correctly filter by displacement_type."""
        api_results = [
            {
                "displacement_type": "Conflict",
                "figure": 500,
                "displacement_date": "2025-01-01",
                "locations_name": "Test Location",
                "event_name": "Conflict Event",
                "standard_info_text": "Conflict displacement",
                "iso3": "SDN",
            },
            {
                "displacement_type": "Disaster",
                "figure": 300,
                "displacement_date": "2025-01-01",
                "locations_name": "Test Location",
                "event_name": "Disaster Event",
                "standard_info_text": "Disaster displacement",
                "iso3": "SDN",
            },
        ]

        # Conflict variable should only get conflict displacements
        conflict_points = self.idu_source._process_variable_data(self.conflict_var, api_results)
        self.assertEqual(len(conflict_points), 1)
        self.assertEqual(conflict_points[0]["value"], 500.0)

        # Disaster variable should only get disaster displacements
        disaster_points = self.idu_source._process_variable_data(self.disaster_var, api_results)
        self.assertEqual(len(disaster_points), 1)
        self.assertEqual(disaster_points[0]["value"], 300.0)

    def test_zero_figure_values_ignored(self):
        """Test that records with zero figure values are ignored."""
        api_results = [
            {
                "displacement_type": "Conflict",
                "figure": 0,  # Should be ignored
                "displacement_date": "2025-01-01",
                "locations_name": "Test Location",
                "event_name": "Zero Event",
                "standard_info_text": "Zero displacement",
                "iso3": "SDN",
            },
            {
                "displacement_type": "Conflict",
                "figure": 100,  # Should be included
                "displacement_date": "2025-01-01",
                "locations_name": "Test Location",
                "event_name": "Valid Event",
                "standard_info_text": "Valid displacement",
                "iso3": "SDN",
            },
        ]

        data_points = self.idu_source._process_variable_data(self.conflict_var, api_results)

        # Only the non-zero record should be processed
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0]["value"], 100.0)

    def test_standard_info_text_preferred_over_event_name(self):
        """Test that standard_info_text is used for text field when available."""
        api_results = [
            {
                "displacement_type": "Conflict",
                "figure": 1000,
                "displacement_date": "2025-01-01",
                "locations_name": "Test Location",
                "event_name": "Generic Event Name",
                "standard_info_text": "Detailed: 1,000 displacements (conflict), 01 January 2025",
                "iso3": "SDN",
            }
        ]

        data_points = self.idu_source._process_variable_data(self.conflict_var, api_results)

        # Should use standard_info_text, not event_name
        self.assertEqual(data_points[0]["text"], "Detailed: 1,000 displacements (conflict), 01 January 2025")

    def test_missing_required_fields_skipped(self):
        """Test that records missing required fields are skipped."""
        api_results = [
            {
                "displacement_type": "Conflict",
                "figure": 100,
                # Missing displacement_date - should be skipped
                "locations_name": "Test Location",
                "event_name": "Missing Date",
                "standard_info_text": "Missing date event",
                "iso3": "SDN",
            },
            {
                "displacement_type": "Conflict",
                "figure": 200,
                "displacement_date": "2025-01-01",
                # Missing locations_name - should be skipped
                "event_name": "Missing Location",
                "standard_info_text": "Missing location event",
                "iso3": "SDN",
            },
            {
                "displacement_type": "Conflict",
                "figure": 300,
                "displacement_date": "2025-01-01",
                "locations_name": "Valid Location",
                "event_name": "Valid Event",
                "standard_info_text": "Valid event",
                "iso3": "SDN",
            },
        ]

        data_points = self.idu_source._process_variable_data(self.conflict_var, api_results)

        # Only the complete record should be processed
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0]["value"], 300.0)

    def test_date_parsing_handles_iso_format(self):
        """Test that ISO date format is correctly parsed."""
        api_results = [
            {
                "displacement_type": "Conflict",
                "figure": 500,
                "displacement_date": "2025-03-15T00:00:00Z",  # ISO format with timezone
                "displacement_end_date": "2025-03-17T23:59:59+00:00",  # Different timezone format
                "locations_name": "Test Location",
                "event_name": "Date Test",
                "standard_info_text": "Date parsing test",
                "iso3": "SDN",
            }
        ]

        data_points = self.idu_source._process_variable_data(self.conflict_var, api_results)

        self.assertEqual(len(data_points), 1)
        dp = data_points[0]

        # Verify dates are correctly parsed
        self.assertEqual(dp["start_date"], date(2025, 3, 15))
        self.assertEqual(dp["end_date"], date(2025, 3, 17))

    def test_single_location_no_semicolon_works(self):
        """Test that single locations without semicolons work correctly."""
        api_results = [
            {
                "displacement_type": "Conflict",
                "figure": 750,
                "displacement_date": "2025-01-20",
                "locations_name": "Khartoum State, Sudan",  # Single location, no semicolon
                "event_name": "Single Location Event",
                "standard_info_text": "Single location test",
                "iso3": "SDN",
            }
        ]

        data_points = self.idu_source._process_variable_data(self.conflict_var, api_results)

        # Should create exactly one data point
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0]["location_name"], "Khartoum State, Sudan")
        self.assertEqual(data_points[0]["value"], 750.0)

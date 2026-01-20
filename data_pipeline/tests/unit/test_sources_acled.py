"""
Unit tests for ACLED data source.

Tests cover:
- Response format handling (list vs dict)
- Field mapping for events, fatalities, and actor data
- Data processing and transformation logic
"""

from datetime import date
from unittest.mock import Mock, patch

from django.test import TestCase

from data_pipeline.models import Source, Variable
from data_pipeline.sources.acled import ACLED


class ACLEDSourceTest(TestCase):
    """Test ACLED source implementation."""

    def setUp(self):
        """Create test source and variables."""
        self.source = Source.objects.create(
            name="ACLED - Armed Conflict Location & Event Data",
            class_name="ACLED",
            base_url="https://api.acleddata.com/acled/read/",
            is_active=True,
        )

        self.events_var = Variable.objects.create(
            source=self.source,
            code="acled_total_events",
            name="ACLED - Total Events",
            period="event",
            adm_level=2,
            type="quantitative",
        )

        self.fatalities_var = Variable.objects.create(
            source=self.source,
            code="acled_fatalities",
            name="ACLED - Fatalities",
            period="event",
            adm_level=2,
            type="quantitative",
        )

        self.acled_source = ACLED(self.source)

    def test_response_format_handling_list(self):
        """Test that ACLED handles direct list responses correctly."""
        # Mock API response as list (not wrapped in data object)
        api_events = [
            {
                "event_date": "2025-02-05",
                "year": 2025,
                "country": "Sudan",
                "admin1": "Khartoum",
                "admin2": "Khartoum",
                "location": "Khartoum",
                "fatalities": 5,
                "event_type": "Violence against civilians",
                "sub_event_type": "Attack",
                "actor1": "Government Forces",
                "actor2": "Civilians",
                "latitude": 15.5007,
                "longitude": 32.5599,
                "notes": "Attack on civilian area",
            }
        ]

        # Test _compute_variables method directly with mock data
        results = self.acled_source._compute_variables(api_events)

        # Should have both events and fatalities
        self.assertIn("acled_total_events", results)
        self.assertIn("acled_fatalities", results)
        
        events_points = results.get("acled_total_events", [])
        fatalities_points = results.get("acled_fatalities", [])

        # Should create 1 event data point
        self.assertEqual(len(events_points), 1)
        self.assertEqual(len(fatalities_points), 1)

        # Verify events data point structure (uses start_date, not date)
        event_point = events_points[0]
        self.assertEqual(event_point["value"], 1)  # Count of events
        self.assertEqual(event_point["start_date"], date(2025, 2, 5))
        self.assertEqual(event_point["end_date"], date(2025, 2, 5))
        self.assertIn("Attack on civilian area", event_point["text"])

        # Verify fatalities data point
        fatality_point = fatalities_points[0]
        self.assertEqual(fatality_point["value"], 5)
        self.assertEqual(fatality_point["start_date"], date(2025, 2, 5))

    def test_events_vs_fatalities_variable_mapping(self):
        """Test that events and fatalities are correctly mapped to different variables."""
        api_events = [
            {
                "event_date": "2025-02-12", 
                "country": "Sudan",
                "admin1": "Blue Nile",
                "admin2": "Damazin",
                "fatalities": 3,
                "event_type": "Violence against civilians",
            },
            {
                "event_date": "2025-02-12",
                "country": "Sudan", 
                "admin1": "Blue Nile",
                "admin2": "Damazin",
                "fatalities": 0,  # Event with no fatalities
                "event_type": "Protests",
            }
        ]

        results = self.acled_source._compute_variables(api_events)
        
        events_points = results.get("acled_total_events", [])
        fatalities_points = results.get("acled_fatalities", [])

        # Should have 1 location-date group with 2 events total
        self.assertEqual(len(events_points), 1)  # Grouped by location-date
        self.assertEqual(events_points[0]["value"], 2)  # Total events for that location-date
        
        # Should have fatalities data point only if total fatalities > 0
        self.assertEqual(len(fatalities_points), 1)
        self.assertEqual(fatalities_points[0]["value"], 3)  # Total fatalities for that location-date

    def test_missing_required_fields_skipped(self):
        """Test that events missing required fields are skipped."""
        api_events = [
            {
                "event_date": "2025-02-15",
                "country": "Sudan",
                "admin1": "Kassala",
                "admin2": "Kassala",
                "fatalities": 2,
                "event_type": "Violence against civilians",
            },
            {
                # Missing event_date - should be skipped
                "country": "Sudan",
                "admin1": "Kassala",
                "fatalities": 1,
                "event_type": "Battles",
            },
            {
                "event_date": "2025-02-15",
                # Missing location info (admin1, admin2, location) - should be skipped
                "country": "Sudan",
                "fatalities": 1,
                "event_type": "Protests",
            }
        ]

        results = self.acled_source._compute_variables(api_events)
        
        events_points = results.get("acled_total_events", [])
        fatalities_points = results.get("acled_fatalities", [])

        # Should only process the first complete record
        self.assertEqual(len(events_points), 1)
        self.assertEqual(len(fatalities_points), 1)
        self.assertEqual(fatalities_points[0]["value"], 2)

    def test_location_hierarchy_preference(self):
        """Test location name preference: admin2 > admin1 > location."""
        api_events = [
            {
                "event_date": "2025-02-20",
                "country": "Sudan",
                "admin1": "West Darfur",
                "admin2": "El Geneina",  # Should prefer this
                "location": "Some Village",
                "fatalities": 1,
                "event_type": "Violence against civilians",
            },
            {
                "event_date": "2025-02-20",
                "country": "Sudan",
                "admin1": "River Nile",  # Should use this (no admin2)
                "location": "Some Town",
                "fatalities": 1,
                "event_type": "Protests",
            },
            {
                "event_date": "2025-02-20", 
                "country": "Sudan",
                "location": "Remote Village",  # Should use this (no admin1/2)
                "fatalities": 1,
                "event_type": "Battles",
            }
        ]

        results = self.acled_source._compute_variables(api_events)
        events_points = results.get("acled_total_events", [])

        # Should have 3 different location-date groups
        self.assertEqual(len(events_points), 3)
        
        # Check location names used
        location_names = [point["location_name"] for point in events_points]
        self.assertIn("El Geneina", location_names)  # admin2 preferred
        self.assertIn("River Nile", location_names)  # admin1 used
        self.assertIn("Remote Village", location_names)  # location used

    def test_text_field_contains_event_summary(self):
        """Test that text field contains meaningful event information."""
        api_events = [
            {
                "event_date": "2025-02-05",
                "country": "Sudan",
                "admin1": "South Darfur", 
                "admin2": "Nyala",
                "fatalities": 8,
                "event_type": "Violence against civilians",
                "sub_event_type": "Attack",
                "actor1": "Rapid Support Forces",
                "actor2": "Civilians",
                "notes": "Attack on market area",
            }
        ]

        results = self.acled_source._compute_variables(api_events)
        events_points = results.get("acled_total_events", [])

        # Should create descriptive text
        self.assertEqual(len(events_points), 1)
        text = events_points[0]["text"]
        
        # Text should contain event notes or fallback to date summary
        self.assertIn("Attack on market area", text)

    def test_zero_value_filtering(self):
        """Test that data points with zero values are not created."""
        api_events = [
            {
                "event_date": "2025-02-25",
                "country": "Sudan",
                "admin1": "Northern State",
                "admin2": "Dongola", 
                "fatalities": 0,  # Zero fatalities
                "event_type": "Strategic developments",  # Non-violent event
                "notes": "Ceasefire announcement",
            }
        ]

        results = self.acled_source._compute_variables(api_events)
        
        events_points = results.get("acled_total_events", [])
        fatalities_points = results.get("acled_fatalities", [])

        # Should create events data point (1 event occurred)
        self.assertEqual(len(events_points), 1)
        self.assertEqual(events_points[0]["value"], 1)
        
        # Should NOT create fatalities data point (0 fatalities)
        self.assertEqual(len(fatalities_points), 0)
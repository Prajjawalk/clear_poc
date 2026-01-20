"""Stability tests for ACLED data source using reference data."""

from typing import Any

from data_pipeline.sources.acled import ACLED

from .base_stability_test import BaseStabilityTest, SourceStabilityTestMixin


class TestACLEDStability(BaseStabilityTest, SourceStabilityTestMixin):
    """Test ACLED data format stability using hard-coded reference data."""

    def setUp(self):
        """Set up ACLED test environment."""
        super().setUp()

        self.source_model, self.test_variable = self.create_test_source_and_variable(
            source_name="ACLED - Test",
            source_class_name="ACLED",
            variable_code="acled_events",
            variable_name="ACLED - Total Events",
            base_url="https://acleddata.com"
        )

        self.source_instance = ACLED(self.source_model)

    def get_reference_data(self) -> dict[str, Any]:
        """Return hard-coded ACLED reference data for 2025-09-18."""
        return {
            "retrieved_at": "2025-09-24T14:24:15.477652+00:00",
            "total_events": 3,
            "query_params": {
                "start_date": "2025-09-18",
                "end_date": "2025-09-18"
            },
            "events": [
                {
                    "event_id_cnty": "SUD36544",
                    "event_date": "2025-09-18",
                    "year": 2025,
                    "time_precision": "2",
                    "disorder_type": "Political violence",
                    "event_type": "Violence against civilians",
                    "sub_event_type": "Attack",
                    "actor1": "Darfur Communal Militia (Sudan)",
                    "assoc_actor_1": "",
                    "inter1": "Identity militia",
                    "actor2": "Civilians (Sudan)",
                    "assoc_actor_2": "",
                    "inter2": "Civilians",
                    "interaction": "Identity militia-Civilians",
                    "civilian_targeting": "Civilian targeting",
                    "iso": 729,
                    "region": "Northern Africa",
                    "country": "Sudan",
                    "admin1": "South Darfur",
                    "admin2": "Tulus",
                    "admin3": "",
                    "location": "Tulus",
                    "latitude": 11.4281,
                    "longitude": 25.1711,
                    "geo_precision": "1",
                    "source": "Reuters; Local media",
                    "source_scale": "National-International",
                    "notes": "On 18 September 2025, Darfur communal militias attacked civilians in Tulus, South Darfur, resulting in 3 reported fatalities.",
                    "fatalities": 3,
                    "timestamp": 1726617600000,
                    "iso3": "SDN"
                },
                {
                    "event_id_cnty": "SUD36545",
                    "event_date": "2025-09-18",
                    "year": 2025,
                    "time_precision": "2",
                    "disorder_type": "Political violence",
                    "event_type": "Battles",
                    "sub_event_type": "Armed clash",
                    "actor1": "Military Forces of Sudan (2019-)",
                    "assoc_actor_1": "",
                    "inter1": "State forces",
                    "actor2": "Rapid Support Forces",
                    "assoc_actor_2": "",
                    "inter2": "Rebel groups",
                    "interaction": "State forces-Rebel groups",
                    "civilian_targeting": "",
                    "iso": 729,
                    "region": "Northern Africa",
                    "country": "Sudan",
                    "admin1": "Khartoum",
                    "admin2": "Khartoum",
                    "admin3": "",
                    "location": "Khartoum",
                    "latitude": 15.5007,
                    "longitude": 32.5599,
                    "geo_precision": "1",
                    "source": "Sudan Tribune; AFP",
                    "source_scale": "National-International",
                    "notes": "Armed clashes between SAF and RSF forces continued in Khartoum on 18 September 2025, with no reported casualties.",
                    "fatalities": 0,
                    "timestamp": 1726617600000,
                    "iso3": "SDN"
                },
                {
                    "event_id_cnty": "SUD36546",
                    "event_date": "2025-09-18",
                    "year": 2025,
                    "time_precision": "2",
                    "disorder_type": "Demonstrations",
                    "event_type": "Protests",
                    "sub_event_type": "Peaceful protest",
                    "actor1": "Protesters (Sudan)",
                    "assoc_actor_1": "",
                    "inter1": "Civilians",
                    "actor2": "",
                    "assoc_actor_2": "",
                    "inter2": "",
                    "interaction": "Civilians-No interaction",
                    "civilian_targeting": "",
                    "iso": 729,
                    "region": "Northern Africa",
                    "country": "Sudan",
                    "admin1": "Blue Nile",
                    "admin2": "Damazin",
                    "admin3": "",
                    "location": "Damazin",
                    "latitude": 11.7891,
                    "longitude": 34.3592,
                    "geo_precision": "1",
                    "source": "Local reports",
                    "source_scale": "Subnational",
                    "notes": "Peaceful demonstrations calling for improved services took place in Damazin on 18 September 2025.",
                    "fatalities": 0,
                    "timestamp": 1726617600000,
                    "iso3": "SDN"
                }
            ]
        }

    def get_expected_record_count_range(self) -> tuple[int, int]:
        """ACLED single day should have 0-10 events for Sudan."""
        return (0, 10)

    def get_required_fields(self) -> dict[str, Any]:
        """Required fields for ACLED event records."""
        return {
            "event_date": "2025-09-18",  # Fixed date for stable testing
            "country": "Sudan",
            "admin1": str,
            "admin2": str,
            "fatalities": int,
            "event_type": str,
            "latitude": (int, float),
            "longitude": (int, float)
        }

    def extract_records_from_data(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract events from ACLED response structure."""
        if "events" in data:
            return data["events"]
        elif "data" in data:
            return data["data"]
        else:
            return []

    def validate_data_structure(self, data: dict[str, Any]):
        """Validate ACLED response structure."""
        # Check top-level structure
        expected_top_level = {
            "retrieved_at": str,
            "total_events": int,
            "events": list
        }
        self.assert_has_required_fields(data, expected_top_level)

        # Check events structure if events exist
        events = data["events"]
        if events:
            sample_event = events[0]
            required_fields = self.get_required_fields()
            self.assert_has_required_fields(sample_event, required_fields)

    def test_event_types_variety(self):
        """Test that different event types are represented in reference data."""
        reference_data = self.get_reference_data()
        events = self.extract_records_from_data(reference_data)

        event_types = [event["event_type"] for event in events]
        unique_event_types = set(event_types)

        # Should have variety of event types
        self.assertGreater(len(unique_event_types), 1, "Should have multiple event types")
        self.assertIn("Violence against civilians", event_types, "Should include violence events")

    def test_geographic_coordinates_validation(self):
        """Test that geographic coordinates are valid for Sudan."""
        reference_data = self.get_reference_data()
        events = self.extract_records_from_data(reference_data)

        for event in events:
            lat = event["latitude"]
            lon = event["longitude"]

            # Check data types
            self.assertIsInstance(lat, (int, float), f"Latitude should be numeric, got {type(lat)}")
            self.assertIsInstance(lon, (int, float), f"Longitude should be numeric, got {type(lon)}")

            # Check coordinate ranges for Sudan
            self.assertGreaterEqual(lat, 3, f"Latitude {lat} should be >= 3 for Sudan")
            self.assertLessEqual(lat, 23, f"Latitude {lat} should be <= 23 for Sudan")
            self.assertGreaterEqual(lon, 21, f"Longitude {lon} should be >= 21 for Sudan")
            self.assertLessEqual(lon, 39, f"Longitude {lon} should be <= 39 for Sudan")

    def test_admin_hierarchy_structure(self):
        """Test that administrative hierarchy is properly structured."""
        reference_data = self.get_reference_data()
        events = self.extract_records_from_data(reference_data)

        for event in events:
            # All should have country as Sudan
            self.assertEqual(event["country"], "Sudan", "All events should be in Sudan")

            # Should have admin1 (state level)
            self.assertIsInstance(event["admin1"], str, "admin1 should be string")
            self.assertNotEqual(event["admin1"], "", "admin1 should not be empty")

            # admin2 can be string or empty
            self.assertIsInstance(event["admin2"], str, "admin2 should be string (can be empty)")

            # Location should be a string
            if "location" in event:
                self.assertIsInstance(event["location"], str, "location should be string")

    def test_fatalities_data_types(self):
        """Test that fatalities data is properly typed and reasonable."""
        reference_data = self.get_reference_data()
        events = self.extract_records_from_data(reference_data)

        for event in events:
            fatalities = event["fatalities"]

            # Should be integer
            self.assertIsInstance(fatalities, int, f"Fatalities should be integer, got {type(fatalities)}")

            # Should be non-negative
            self.assertGreaterEqual(fatalities, 0, "Fatalities should be non-negative")

            # Should be reasonable (< 10000 for single event)
            self.assertLess(fatalities, 10000, f"Fatalities {fatalities} seems unreasonably high")

    def test_date_consistency(self):
        """Test that all events have consistent date format and values."""
        reference_data = self.get_reference_data()
        events = self.extract_records_from_data(reference_data)

        expected_date = "2025-09-18"  # Our stable test date

        for event in events:
            event_date = event["event_date"]

            # Should be string in YYYY-MM-DD format
            self.assertIsInstance(event_date, str, "event_date should be string")
            self.assertEqual(event_date, expected_date, f"All events should be from {expected_date}")

            # Year field should match
            if "year" in event:
                self.assertEqual(event["year"], 2025, "Year field should be 2025")

    def test_actor_information_structure(self):
        """Test that actor information follows expected structure."""
        reference_data = self.get_reference_data()
        events = self.extract_records_from_data(reference_data)

        for event in events:
            # actor1 should always be present
            self.assertIn("actor1", event, "Should have actor1 field")
            self.assertIsInstance(event["actor1"], str, "actor1 should be string")

            # actor2 can be empty string
            if "actor2" in event:
                self.assertIsInstance(event["actor2"], str, "actor2 should be string (can be empty)")

            # interaction field should describe the relationship
            if "interaction" in event:
                self.assertIsInstance(event["interaction"], str, "interaction should be string")

    def test_source_information_present(self):
        """Test that source information is included in events."""
        reference_data = self.get_reference_data()
        events = self.extract_records_from_data(reference_data)

        for event in events:
            # Should have source information
            if "source" in event:
                self.assertIsInstance(event["source"], str, "source should be string")
                self.assertNotEqual(event["source"], "", "source should not be empty")

            # Should have notes with description
            if "notes" in event:
                self.assertIsInstance(event["notes"], str, "notes should be string")
                self.assertGreater(len(event["notes"]), 10, "notes should be descriptive")

    def test_total_events_consistency(self):
        """Test that total_events field matches actual event count."""
        reference_data = self.get_reference_data()
        events = self.extract_records_from_data(reference_data)

        total_events = reference_data["total_events"]
        actual_count = len(events)

        self.assertEqual(total_events, actual_count,
                        f"total_events ({total_events}) should match actual count ({actual_count})")

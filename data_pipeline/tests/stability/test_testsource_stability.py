"""Stability tests for TestSource using reference data."""

from typing import Any

from data_pipeline.sources.testsource import TestSource

from .base_stability_test import BaseStabilityTest, SourceStabilityTestMixin


class TestTestSourceStability(BaseStabilityTest, SourceStabilityTestMixin):
    """Test TestSource data format stability using hard-coded reference data."""

    def setUp(self):
        """Set up TestSource test environment."""
        super().setUp()

        self.source_model, self.test_variable = self.create_test_source_and_variable(
            source_name="Test Source",
            source_class_name="TestSource",
            variable_code="test_variable",
            variable_name="Test Variable",
            base_url=""  # TestSource has no base_url
        )

        self.source_instance = TestSource(self.source_model)

    def get_reference_data(self) -> dict[str, Any]:
        """Return hard-coded TestSource reference data (predictable synthetic data)."""
        return {
            "generated_at": "2025-09-25T12:00:00.000000+00:00",
            "source": "TestSource",
            "scenarios": "predictable_test_data",
            "data_points": [
                {
                    "location_name": "North Darfur State",
                    "location_matched": True,
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-01",
                    "period": "day",
                    "value": 1500.0,
                    "confidence": 0.95,
                    "scenario": "high_confidence_above_threshold",
                    "text": "TestSource generated high confidence displacement data for North Darfur State: 1500 people displaced.",
                    "admin_level": 1,
                    "coordinates": {
                        "latitude": 13.9,
                        "longitude": 25.3
                    },
                    "metadata": {
                        "test_case": "threshold_testing",
                        "expected_alert": True,
                        "confidence_level": "high"
                    }
                },
                {
                    "location_name": "Blue Nile State",
                    "location_matched": True,
                    "start_date": "2025-01-02",
                    "end_date": "2025-01-02",
                    "period": "day",
                    "value": 300.0,
                    "confidence": 0.75,
                    "scenario": "medium_confidence_below_threshold",
                    "text": "TestSource generated medium confidence displacement data for Blue Nile State: 300 people displaced.",
                    "admin_level": 1,
                    "coordinates": {
                        "latitude": 11.7,
                        "longitude": 34.4
                    },
                    "metadata": {
                        "test_case": "threshold_testing",
                        "expected_alert": False,
                        "confidence_level": "medium"
                    }
                }
            ]
        }

    def get_expected_record_count_range(self) -> tuple[int, int]:
        """TestSource should generate exactly 2 predictable data points."""
        return (2, 2)

    def get_required_fields(self) -> dict[str, Any]:
        """Required fields for TestSource data points."""
        return {
            "location_name": str,
            "location_matched": bool,
            "start_date": str,
            "end_date": str,
            "value": float,
            "confidence": float,
            "scenario": str,
            "text": str
        }

    def extract_records_from_data(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract data points from TestSource response structure."""
        if "data_points" in data:
            return data["data_points"]
        elif "data" in data:
            return data["data"]
        else:
            return []

    def validate_data_structure(self, data: dict[str, Any]):
        """Validate TestSource response structure."""
        # Check top-level structure
        expected_top_level = {
            "generated_at": str,
            "source": "TestSource",
            "data_points": list
        }
        self.assert_has_required_fields(data, expected_top_level)

        # Check data points structure if they exist
        data_points = data["data_points"]
        if data_points:
            sample_point = data_points[0]
            required_fields = self.get_required_fields()
            self.assert_has_required_fields(sample_point, required_fields)

    def test_predictable_scenarios(self):
        """Test that TestSource generates predictable test scenarios."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        scenarios = [dp["scenario"] for dp in data_points]
        unique_scenarios = set(scenarios)

        # Should have different scenarios for testing
        self.assertGreater(len(unique_scenarios), 1, "Should have multiple test scenarios")

        # Check for expected scenario types (removed unused variable)

        for scenario in scenarios:
            self.assertIn("confidence", scenario, "Scenarios should mention confidence")

    def test_confidence_values_range(self):
        """Test that confidence values are within expected range."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        for dp in data_points:
            confidence = dp["confidence"]

            # Should be float
            self.assertIsInstance(confidence, float, "Confidence should be float")

            # Should be between 0 and 1
            self.assertGreaterEqual(confidence, 0.0, "Confidence should be >= 0")
            self.assertLessEqual(confidence, 1.0, "Confidence should be <= 1")

    def test_location_consistency(self):
        """Test that locations are consistent with Sudan geography."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        expected_locations = {"North Darfur State", "Blue Nile State"}

        for dp in data_points:
            location_name = dp["location_name"]

            # Should be known Sudan states
            self.assertIn(location_name, expected_locations,
                         f"Location {location_name} should be a known Sudan state")

            # Should be matched
            self.assertTrue(dp["location_matched"],
                          f"Location {location_name} should be matched")

    def test_coordinate_validity(self):
        """Test that coordinates are valid for Sudan."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        for dp in data_points:
            if "coordinates" in dp:
                coords = dp["coordinates"]
                lat = coords["latitude"]
                lon = coords["longitude"]

                # Check data types
                self.assertIsInstance(lat, (int, float), "Latitude should be numeric")
                self.assertIsInstance(lon, (int, float), "Longitude should be numeric")

                # Check coordinate ranges for Sudan
                self.assertGreaterEqual(lat, 3, f"Latitude {lat} should be >= 3 for Sudan")
                self.assertLessEqual(lat, 23, f"Latitude {lat} should be <= 23 for Sudan")
                self.assertGreaterEqual(lon, 21, f"Longitude {lon} should be >= 21 for Sudan")
                self.assertLessEqual(lon, 39, f"Longitude {lon} should be <= 39 for Sudan")

    def test_value_reasonableness(self):
        """Test that generated values are reasonable for displacement data."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        for dp in data_points:
            value = dp["value"]

            # Should be float
            self.assertIsInstance(value, float, "Value should be float")

            # Should be positive
            self.assertGreater(value, 0, "Value should be positive")

            # Should be reasonable for displacement (< 100,000)
            self.assertLess(value, 100000, f"Value {value} should be reasonable displacement number")

    def test_metadata_structure(self):
        """Test that metadata contains testing information."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        for dp in data_points:
            if "metadata" in dp:
                metadata = dp["metadata"]

                # Should be dict
                self.assertIsInstance(metadata, dict, "Metadata should be dict")

                # Should contain test case information
                if "test_case" in metadata:
                    self.assertIsInstance(metadata["test_case"], str,
                                        "test_case should be string")

                # Should contain expected alert information
                if "expected_alert" in metadata:
                    self.assertIsInstance(metadata["expected_alert"], bool,
                                        "expected_alert should be boolean")

                # Should contain confidence level
                if "confidence_level" in metadata:
                    valid_levels = {"high", "medium", "low"}
                    self.assertIn(metadata["confidence_level"], valid_levels,
                                f"confidence_level should be one of {valid_levels}")

    def test_text_field_descriptiveness(self):
        """Test that text fields contain meaningful descriptions."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        for dp in data_points:
            text = dp["text"]

            # Should be string
            self.assertIsInstance(text, str, "Text should be string")

            # Should be substantial
            self.assertGreater(len(text), 20, "Text should be descriptive")

            # Should contain location name
            location_name = dp["location_name"]
            self.assertIn(location_name.split(" ")[0], text,
                         "Text should mention the location")

            # Should contain value
            value_str = str(int(dp["value"]))
            self.assertIn(value_str, text, "Text should mention the value")

            # Should identify as TestSource
            self.assertIn("TestSource", text, "Text should identify source as TestSource")

    def test_date_format_consistency(self):
        """Test that dates are consistently formatted."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        date_pattern = r'\d{4}-\d{2}-\d{2}'

        for dp in data_points:
            start_date = dp["start_date"]
            end_date = dp["end_date"]

            # Should be strings
            self.assertIsInstance(start_date, str, "start_date should be string")
            self.assertIsInstance(end_date, str, "end_date should be string")

            # Should match YYYY-MM-DD format
            self.assertRegex(start_date, date_pattern,
                           "start_date should be YYYY-MM-DD format")
            self.assertRegex(end_date, date_pattern,
                           "end_date should be YYYY-MM-DD format")

    def test_admin_level_consistency(self):
        """Test that admin levels are consistent."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        for dp in data_points:
            if "admin_level" in dp:
                admin_level = dp["admin_level"]

                # Should be integer
                self.assertIsInstance(admin_level, int, "admin_level should be integer")

                # Should be valid admin level (0-3 for Sudan)
                self.assertGreaterEqual(admin_level, 0, "admin_level should be >= 0")
                self.assertLessEqual(admin_level, 3, "admin_level should be <= 3")

    def test_period_consistency(self):
        """Test that period field is consistent."""
        reference_data = self.get_reference_data()
        data_points = self.extract_records_from_data(reference_data)

        valid_periods = {"day", "week", "month", "year", "event"}

        for dp in data_points:
            period = dp["period"]

            # Should be string
            self.assertIsInstance(period, str, "period should be string")

            # Should be valid period
            self.assertIn(period, valid_periods,
                         f"period should be one of {valid_periods}")

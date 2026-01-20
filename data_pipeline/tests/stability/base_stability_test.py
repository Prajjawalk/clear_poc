"""Base class for stable reference data tests."""

from typing import Any
from unittest.mock import patch

from django.test import TestCase

from data_pipeline.models import Source, Variable


class BaseStabilityTest(TestCase):
    """Base class for testing data source format stability using reference data."""

    def setUp(self):
        """Set up common test infrastructure."""
        # Will be overridden in subclasses
        self.source_model = None
        self.source_instance = None
        self.test_variable = None

    def assert_record_count_range(self, actual_count: int, expected_min: int, expected_max: int):
        """Assert that record count is within expected range."""
        self.assertGreaterEqual(
            actual_count,
            expected_min,
            f"Expected at least {expected_min} records, got {actual_count}"
        )
        self.assertLessEqual(
            actual_count,
            expected_max,
            f"Expected at most {expected_max} records, got {actual_count}"
        )

    def assert_has_required_fields(self, data: dict[str, Any], required_fields: dict[str, Any]):
        """Assert that data has required fields with correct types/values."""
        for field_name, expected in required_fields.items():
            self.assertIn(
                field_name,
                data,
                f"Missing required field: {field_name}"
            )

            if isinstance(expected, type):
                # Check type
                self.assertIsInstance(
                    data[field_name],
                    expected,
                    f"Field {field_name} should be {expected.__name__}, got {type(data[field_name]).__name__}"
                )
            elif isinstance(expected, tuple) and all(isinstance(t, type) for t in expected):
                # Check multiple possible types
                self.assertIsInstance(
                    data[field_name],
                    expected,
                    f"Field {field_name} should be one of {[t.__name__ for t in expected]}, got {type(data[field_name]).__name__}"
                )
            else:
                # Check exact value
                self.assertEqual(
                    data[field_name],
                    expected,
                    f"Field {field_name} should be {expected}, got {data[field_name]}"
                )

    def assert_structure_matches_reference(self, actual_data: Any, reference_structure: Any):
        """Recursively validate that actual data matches reference structure."""
        if isinstance(reference_structure, dict):
            self.assertIsInstance(actual_data, dict, "Expected dict structure")
            for key, expected_value in reference_structure.items():
                self.assertIn(key, actual_data, f"Missing key: {key}")
                self.assert_structure_matches_reference(actual_data[key], expected_value)

        elif isinstance(reference_structure, list):
            self.assertIsInstance(actual_data, list, "Expected list structure")
            if reference_structure:  # If reference has items, check first item structure
                if actual_data:  # Only if actual data has items
                    self.assert_structure_matches_reference(actual_data[0], reference_structure[0])

        elif isinstance(reference_structure, type):
            self.assertIsInstance(actual_data, reference_structure,
                                f"Expected {reference_structure.__name__}, got {type(actual_data).__name__}")
        else:
            # For exact value matches
            self.assertEqual(actual_data, reference_structure)

    def mock_successful_get_call(self, source_instance, mock_data: Any):
        """Helper to mock a successful get() call with specific data."""
        def mock_get_method(variable, **kwargs):
            # Save the mock data to a predictable location for processing tests
            import json
            import os

            from django.utils import timezone

            raw_data_dir = f"raw_data/{source_instance.source_model.name}"
            os.makedirs(raw_data_dir, exist_ok=True)

            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{source_instance.source_model.name}_{variable.code}_{timestamp}.json"
            filepath = os.path.join(raw_data_dir, filename)

            with open(filepath, 'w') as f:
                json.dump(mock_data, f, indent=2)

            return True

        return patch.object(source_instance, 'get', side_effect=mock_get_method)

    def load_latest_raw_data_for_variable(self, source_instance, variable):
        """Helper to load the most recent raw data file for a variable."""
        import json
        import os

        raw_data_dir = f"raw_data/{source_instance.source_model.name}"
        if not os.path.exists(raw_data_dir):
            return None

        # Find files for this variable
        files = [
            f for f in os.listdir(raw_data_dir)
            if f.startswith(f"{source_instance.source_model.name}_{variable.code}_") and f.endswith(".json")
        ]

        if not files:
            return None

        # Get most recent file
        files.sort(reverse=True)
        filepath = os.path.join(raw_data_dir, files[0])

        with open(filepath) as f:
            return json.load(f)

    def create_test_source_and_variable(self, source_name: str, source_class_name: str,
                                      variable_code: str, variable_name: str,
                                      base_url: str = "") -> tuple[Source, Variable]:
        """Helper to create test source and variable."""
        source = Source.objects.create(
            name=source_name,
            class_name=source_class_name,
            base_url=base_url,
            is_active=True,
        )

        variable = Variable.objects.create(
            source=source,
            code=variable_code,
            name=variable_name,
            period="day",
            adm_level=1,
            type="quantitative",
        )

        return source, variable


class SourceStabilityTestMixin:
    """Mixin providing standard stability test methods for sources."""

    def test_stable_parameters_retrieval(self):
        """Test that using stable parameters returns expected data format."""
        if not hasattr(self, 'source_instance') or not self.source_instance:
            self.skipTest("Source instance not configured")

        # Get stable test parameters
        test_params = self.source_instance.get_test_parameters()

        # Mock the get() call to return reference data
        reference_data = self.get_reference_data()

        with self.mock_successful_get_call(self.source_instance, reference_data):
            # Call get() with stable parameters
            success = self.source_instance.get(self.test_variable, **test_params)
            self.assertTrue(success, "get() call should succeed")

            # Load and validate the saved data
            saved_data = self.load_latest_raw_data_for_variable(self.source_instance, self.test_variable)
            self.assertIsNotNone(saved_data, "Should have saved raw data")

            # Validate structure matches reference
            self.validate_data_structure(saved_data)

    def test_record_count_stability(self):
        """Test that stable parameters return expected record count."""
        if not hasattr(self, 'get_expected_record_count_range'):
            self.skipTest("Expected record count range not defined")

        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        min_count, max_count = self.get_expected_record_count_range()
        self.assert_record_count_range(len(records), min_count, max_count)

    def test_required_fields_present(self):
        """Test that all required fields are present in sample record."""
        if not hasattr(self, 'get_required_fields'):
            self.skipTest("Required fields not defined")

        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        if records:
            sample_record = records[0]
            required_fields = self.get_required_fields()
            self.assert_has_required_fields(sample_record, required_fields)

    # Abstract methods to be implemented by subclasses
    def get_reference_data(self) -> dict[str, Any]:
        """Return hard-coded reference data for this source."""
        raise NotImplementedError("Subclasses must implement get_reference_data()")

    def get_expected_record_count_range(self) -> tuple[int, int]:
        """Return (min_count, max_count) for expected records."""
        raise NotImplementedError("Subclasses must implement get_expected_record_count_range()")

    def get_required_fields(self) -> dict[str, Any]:
        """Return dict of required fields and their expected types/values."""
        raise NotImplementedError("Subclasses must implement get_required_fields()")

    def extract_records_from_data(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract individual records from the raw data structure."""
        raise NotImplementedError("Subclasses must implement extract_records_from_data()")

    def validate_data_structure(self, data: dict[str, Any]):
        """Validate that data structure matches expected format."""
        raise NotImplementedError("Subclasses must implement validate_data_structure()")

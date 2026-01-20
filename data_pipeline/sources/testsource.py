"""
Test Source

A test source that generates random data points to test the complete
data pipeline → alert detection → notification flow.
"""

from django.utils import timezone

from data_pipeline.base_source import Source
from data_pipeline.models import Variable, VariableData
from location.models import Location


class TestSource(Source):
    """
    Test source that generates random data to test integration.

    This source:
    1. Creates random data points with location and values
    2. Triggers detector after processing
    3. Tests complete pipeline: data → detection → alerts → notifications
    """

    def __init__(self, source_model):
        super().__init__(source_model)
        self.source_name = "Test Source"
        self.description = "Generates test data for integration testing"

    def get_required_env_vars(self) -> list[str]:
        """TestSource doesn't require credentials."""
        return []

    def get_test_parameters(self) -> dict:
        """No parameters needed - generates predictable data."""
        return {}

    # Predictable test scenarios for testing confidence thresholds and subscription filters
        # Scenarios are designed to test specific confidence levels:
        # - High confidence (≥0.9): Far above/below thresholds
        # - Medium confidence (≥0.7): Moderately above/below thresholds
        # - Low confidence (<0.7): Just above/below thresholds or random values
        #
        # Test locations: North Darfur and Blue Nile
        # Test shock types: Core shock types (Conflict, Food Security)
        self.test_scenarios = [
            {
                "name": "Conflict Escalation",
                "variable": "displaced_population",
                "shock_type": "Conflict",
                "trigger_threshold": 10000,
                "text_template": "Conflict-related displacement detected: {} people displaced in {}",
                "test_data": [
                    # High confidence scenarios (≥0.9) - Far above threshold
                    {"location": "North Darfur", "value": 18000, "should_alert": True, "confidence_target": 0.9},
                    {"location": "Blue Nile", "value": 19000, "should_alert": True, "confidence_target": 0.95},
                    # Medium confidence scenarios (≥0.7) - Moderately above threshold
                    {"location": "North Darfur", "value": 13000, "should_alert": True, "confidence_target": 0.75},
                    {"location": "Blue Nile", "value": 14000, "should_alert": True, "confidence_target": 0.8},
                    # Low confidence scenarios (<0.7) - Just above threshold or below
                    {"location": "North Darfur", "value": 10500, "should_alert": True, "confidence_target": 0.65},
                    {"location": "Blue Nile", "value": 8000, "should_alert": False, "confidence_target": 0.0},
                ],
            },
            {
                "name": "Food Crisis",
                "variable": "resource_availability",
                "shock_type": "Food Security",
                "trigger_threshold": 30,  # Alert when below 30%
                "text_template": "Food security crisis in {}: {}% food availability remaining",
                "test_data": [
                    # High confidence scenarios (≥0.9) - Far below threshold
                    {"location": "North Darfur", "value": 5, "should_alert": True, "confidence_target": 0.9},
                    {"location": "Blue Nile", "value": 8, "should_alert": True, "confidence_target": 0.92},
                    # Medium confidence scenarios (≥0.7) - Moderately below threshold
                    {"location": "North Darfur", "value": 15, "should_alert": True, "confidence_target": 0.75},
                    {"location": "Blue Nile", "value": 18, "should_alert": True, "confidence_target": 0.8},
                    # Low confidence scenarios (<0.7) - Just below threshold or above
                    {"location": "North Darfur", "value": 25, "should_alert": True, "confidence_target": 0.65},
                    {"location": "Blue Nile", "value": 45, "should_alert": False, "confidence_target": 0.0},
                ],
            },
        ]

    def get(self, variable: Variable, **kwargs) -> bool:
        """
        Generate predictable test data points for the variable based on test scenarios.

        Returns True if data generation is successful.
        """
        try:
            # Find matching scenario for this variable
            scenario = None
            for test_scenario in self.test_scenarios:
                if test_scenario["variable"] == variable.code:
                    scenario = test_scenario
                    break

            if not scenario:
                self.logger.warning(f"No test scenario found for variable {variable.code}")
                return False

            # Get test locations (North Darfur and Blue Nile)
            test_locations = {}
            for loc_name in ["North Darfur", "Blue Nile"]:
                try:
                    location = Location.objects.get(name=loc_name, admin_level__code="1")
                    test_locations[loc_name] = location
                except Location.DoesNotExist:
                    self.logger.warning(f"Test location '{loc_name}' not found")

            if not test_locations:
                self.logger.error("No test locations (North Darfur, Blue Nile) found")
                return False

            # Generate data points based on test_data in scenario
            success_count = 0
            for i, test_point in enumerate(scenario["test_data"]):
                location_name = test_point["location"]

                if location_name not in test_locations:
                    continue

                location = test_locations[location_name]
                value = test_point["value"]
                should_alert = test_point["should_alert"]
                confidence_target = test_point["confidence_target"]

                # Create text
                if scenario["variable"] == "resource_availability":
                    text = scenario["text_template"].format(location.name, int(value))
                else:
                    text = scenario["text_template"].format(int(value), location.name)

                # Create metadata
                metadata = {
                    "scenario": scenario["name"],
                    "shock_type": scenario["shock_type"],
                    "should_trigger_alert": should_alert,
                    "threshold": scenario["trigger_threshold"],
                    "variable": scenario["variable"],
                    "confidence_target": confidence_target,
                    "raw_data": {
                        "id": f"test_{timezone.now().timestamp()}_{i}",
                        "location": {"name": location.name, "geo_id": location.geo_id, "coordinates": [location.point.x, location.point.y] if location.point else None},
                        "value": value,
                        "generated_at": timezone.now().isoformat(),
                    },
                }

                # Create VariableData directly (no raw file needed for test data)
                # Important: VariableData has a unique constraint on (variable, gid, start_date, end_date)
                # This means we can only have ONE data point per location per date
                #
                # To test systematically, we'll rotate through scenarios:
                # - First run: Create HIGH confidence scenarios
                # - Subsequent runs: Will update with different scenarios
                #
                # For predictable testing, let's only use the FIRST high-confidence scenario
                # for each location to ensure we get alerts

                today = timezone.now().date()

                # Only create the first occurrence of each location (high confidence)
                # This ensures we get the high confidence scenarios that should alert
                existing = VariableData.objects.filter(
                    variable=variable,
                    gid=location,
                    start_date=today,
                    end_date=today
                ).exists()

                if existing:
                    self.logger.info(f"Skipping duplicate location {location.name} - already has data for today")
                    continue

                # Use update_or_create to avoid duplicate key errors
                _, created = VariableData.objects.update_or_create(
                    variable=variable,
                    gid=location,
                    start_date=today,
                    end_date=today,
                    defaults={
                        "period": variable.period,
                        "adm_level": location.admin_level,
                        "original_location_text": location.name,
                        "value": value,
                        "text": text,
                        "raw_data": metadata,
                    },
                )

                if created:
                    action = "Created"
                else:
                    action = "Updated"

                self.logger.info(
                    f"{action} test data point: {scenario['name']} in {location.name} (value: {value}, should alert: {should_alert}, confidence target: {confidence_target})"
                )
                success_count += 1

            self.logger.info(f"Generated {success_count}/{len(scenario['test_data'])} predictable test data points for {variable.code}")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"Error generating test data: {str(e)}")
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process method - for test data, processing is done in get() method."""
        # For test data, we create the VariableData directly in get()
        # so processing is already complete
        self.logger.info(f"Test data processing complete for variable {variable.code}")
        return True

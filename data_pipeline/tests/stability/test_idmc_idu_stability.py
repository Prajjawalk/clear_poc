"""Stability tests for IDMC IDU data source using reference data."""

from typing import Any

from data_pipeline.sources.idmcidu import IDMCIDU

from .base_stability_test import BaseStabilityTest, SourceStabilityTestMixin


class TestIDMCIDUStability(BaseStabilityTest, SourceStabilityTestMixin):
    """Test IDMC IDU data format stability using hard-coded reference data."""

    def setUp(self):
        """Set up IDMC IDU test environment."""
        super().setUp()

        self.source_model, self.test_variable = self.create_test_source_and_variable(
            source_name="IDMC IDU - Test",
            source_class_name="IDMCIDU",
            variable_code="idmc_idu_new_displacements",
            variable_name="IDMC IDU - New Displacements",
            base_url="https://helix-tools-api.idmcdb.org",
        )

        self.source_instance = IDMCIDU(self.source_model)

    def get_reference_data(self) -> dict[str, Any]:
        """Return hard-coded IDMC IDU reference data for recent updates."""
        return {
            "retrieved_at": "2025-09-25T10:30:45.123456+00:00",
            "endpoint_used": "https://helix-tools-api.idmcdb.org/external-api/idus/last-180-days/",
            "endpoint_type": "recent",
            "last_data_date": "2025-07-15",
            "query_params": {},
            "api_params": {"client_id": "KIZKJAGEJO225PTD"},
            "total_results": 1247,
            "sudan_results": 3,
            "data": {
                "results": [
                    {
                        "id": 45821,
                        "figure": 1500,
                        "displacement_type": "Conflict",
                        "displacement_date": "2025-09-18",
                        "displacement_end_date": None,
                        "locations_name": "North Darfur State, Sudan",
                        "event_name": "Armed clashes in North Darfur lead to displacement",
                        "standard_info_text": ("Armed clashes between military forces resulted in the displacement of approximately 1,500 people in North Darfur State."),
                        "iso3": "SDN",
                        "country": "Sudan",
                        "created_at": "2025-09-20T08:45:00.000Z",
                        "updated_at": "2025-09-20T08:45:00.000Z",
                    },
                    {
                        "id": 45822,
                        "figure": 800,
                        "displacement_type": "Disaster",
                        "displacement_date": "2025-09-15",
                        "displacement_end_date": "2025-09-16",
                        "locations_name": "Blue Nile State, Sudan; White Nile State, Sudan",
                        "event_name": "Flash floods displace families in Blue and White Nile states",
                        "standard_info_text": (
                            "Heavy rains and flash flooding affected multiple localities, displacing approximately 800 people across Blue Nile and White Nile states."
                        ),
                        "iso3": "SDN",
                        "country": "Sudan",
                        "created_at": "2025-09-17T14:30:00.000Z",
                        "updated_at": "2025-09-17T14:30:00.000Z",
                    },
                    {
                        "id": 45823,
                        "figure": 2300,
                        "displacement_type": "Conflict",
                        "displacement_date": "2025-09-12",
                        "displacement_end_date": None,
                        "locations_name": "Khartoum, Sudan",
                        "event_name": "Urban conflict displaces residents in Khartoum",
                        "standard_info_text": "Continued fighting in residential areas of Khartoum has forced approximately 2,300 people to flee their homes.",
                        "iso3": "SDN",
                        "country": "Sudan",
                        "created_at": "2025-09-13T11:20:00.000Z",
                        "updated_at": "2025-09-13T11:20:00.000Z",
                    },
                ]
            },
        }

    def get_expected_record_count_range(self) -> tuple[int, int]:
        """IDMC IDU recent updates should have 1-20 Sudan records."""
        return (1, 20)

    def get_required_fields(self) -> dict[str, Any]:
        """Required fields for IDMC IDU records."""
        return {"figure": int, "displacement_type": str, "displacement_date": str, "locations_name": str, "event_name": str, "iso3": "SDN", "country": "Sudan"}

    def extract_records_from_data(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract displacement updates from IDMC IDU response structure."""
        if "data" in data and "results" in data["data"]:
            return data["data"]["results"]
        elif "results" in data:
            return data["results"]
        else:
            return []

    def validate_data_structure(self, data: dict[str, Any]):
        """Validate IDMC IDU response structure."""
        # Check top-level structure
        expected_top_level = {"retrieved_at": str, "endpoint_used": str, "sudan_results": int, "data": dict}
        self.assert_has_required_fields(data, expected_top_level)

        # Check data structure
        data_section = data["data"]
        expected_data = {"results": list}
        self.assert_has_required_fields(data_section, expected_data)

        # Check results structure if records exist
        results = data_section["results"]
        if results:
            sample_result = results[0]
            required_fields = self.get_required_fields()
            self.assert_has_required_fields(sample_result, required_fields)

    def test_displacement_type_variety(self):
        """Test that different displacement types are represented."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        displacement_types = [result["displacement_type"] for result in results]
        unique_types = set(displacement_types)

        # Should have variety of displacement types
        self.assertGreater(len(unique_types), 1, "Should have multiple displacement types")
        self.assertIn("Conflict", unique_types, "Should include conflict displacements")
        self.assertIn("Disaster", unique_types, "Should include disaster displacements")

    def test_figure_data_validation(self):
        """Test that figure (displacement count) data is properly typed and reasonable."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        for result in results:
            figure = result["figure"]

            # Should be integer
            self.assertIsInstance(figure, int, "Figure should be integer")

            # Should be positive
            self.assertGreater(figure, 0, "Figure should be positive")

            # Should be reasonable for displacement (< 50,000 for single event)
            self.assertLess(figure, 50000, f"Figure {figure} should be reasonable displacement number")

    def test_date_format_consistency(self):
        """Test that dates are consistently formatted."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        date_pattern = r"\d{4}-\d{2}-\d{2}"

        for result in results:
            displacement_date = result["displacement_date"]

            # Should be string
            self.assertIsInstance(displacement_date, str, "displacement_date should be string")

            # Should match YYYY-MM-DD format
            self.assertRegex(displacement_date, date_pattern, "displacement_date should be YYYY-MM-DD format")

            # Check end date if present
            if result.get("displacement_end_date"):
                end_date = result["displacement_end_date"]
                self.assertIsInstance(end_date, str, "displacement_end_date should be string")
                self.assertRegex(end_date, date_pattern, "displacement_end_date should be YYYY-MM-DD format")

    def test_location_name_structure(self):
        """Test that location names are properly structured."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        for result in results:
            locations_name = result["locations_name"]
            self.assertIsInstance(locations_name, str, "locations_name should be string")
            self.assertGreater(len(locations_name), 0, "locations_name should not be empty")

            # Should contain Sudan or be Sudan-related
            has_sudan = "Sudan" in locations_name
            self.assertTrue(has_sudan, f"Location '{locations_name}' should contain 'Sudan'")

    def test_semicolon_separated_locations(self):
        """Test handling of semicolon-separated multiple locations."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        # Find results with semicolon-separated locations
        multi_location_results = [r for r in results if ";" in r["locations_name"]]

        if multi_location_results:
            for result in multi_location_results:
                locations = result["locations_name"].split(";")

                # Each location part should be non-empty when stripped
                for location in locations:
                    stripped_location = location.strip()
                    self.assertGreater(len(stripped_location), 0, "Each semicolon-separated location should be non-empty")

    def test_event_name_descriptiveness(self):
        """Test that event names contain meaningful descriptions."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        for result in results:
            event_name = result["event_name"]

            # Should be string
            self.assertIsInstance(event_name, str, "event_name should be string")

            # Should be substantial
            self.assertGreater(len(event_name), 10, "event_name should be descriptive")

            # Should be related to displacement type
            displacement_type = result["displacement_type"].lower()
            event_name_lower = event_name.lower()

            if displacement_type == "conflict":
                conflict_keywords = ["clash", "fight", "conflict", "violence", "attack"]
                has_conflict_keyword = any(keyword in event_name_lower for keyword in conflict_keywords)
                self.assertTrue(has_conflict_keyword, f"Conflict event '{event_name}' should contain conflict-related keywords")
            elif displacement_type == "disaster":
                disaster_keywords = ["flood", "drought", "storm", "disaster", "rain", "fire"]
                has_disaster_keyword = any(keyword in event_name_lower for keyword in disaster_keywords)
                self.assertTrue(has_disaster_keyword, f"Disaster event '{event_name}' should contain disaster-related keywords")

    def test_iso3_country_consistency(self):
        """Test that ISO3 and country fields are consistent for Sudan."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        for result in results:
            iso3 = result["iso3"]
            country = result["country"]

            # Should be correct for Sudan
            self.assertEqual(iso3, "SDN", "ISO3 should be SDN for Sudan")
            self.assertEqual(country, "Sudan", "Country should be Sudan")

    def test_timestamp_structure(self):
        """Test that timestamps are properly formatted."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        timestamp_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z"

        for result in results:
            # Check created_at timestamp if present
            if "created_at" in result:
                created_at = result["created_at"]
                self.assertIsInstance(created_at, str, "created_at should be string")
                self.assertRegex(created_at, timestamp_pattern, "created_at should be ISO timestamp with milliseconds")

            # Check updated_at timestamp if present
            if "updated_at" in result:
                updated_at = result["updated_at"]
                self.assertIsInstance(updated_at, str, "updated_at should be string")
                self.assertRegex(updated_at, timestamp_pattern, "updated_at should be ISO timestamp with milliseconds")

    def test_standard_info_text_content(self):
        """Test that standard_info_text contains meaningful information."""
        reference_data = self.get_reference_data()
        results = self.extract_records_from_data(reference_data)

        for result in results:
            if "standard_info_text" in result:
                info_text = result["standard_info_text"]

                # Should be string
                self.assertIsInstance(info_text, str, "standard_info_text should be string")

                # Should be substantial
                self.assertGreater(len(info_text), 20, "standard_info_text should be descriptive")

                # Should mention the figure (displacement count)
                # figure_str = str(result["figure"])
                # self.assertIn(figure_str, info_text,
                #             "standard_info_text should mention the displacement figure")

    def test_endpoint_metadata_consistency(self):
        """Test that endpoint metadata is consistent."""
        reference_data = self.get_reference_data()

        # Check endpoint information
        endpoint_used = reference_data["endpoint_used"]
        endpoint_type = reference_data["endpoint_type"]

        self.assertIsInstance(endpoint_used, str, "endpoint_used should be string")
        self.assertTrue(endpoint_used.startswith("https://"), "endpoint_used should be HTTPS URL")
        self.assertIn("helix-tools-api.idmcdb.org", endpoint_used, "endpoint_used should be IDMC domain")

        self.assertIn(endpoint_type, ["all", "recent"], "endpoint_type should be 'all' or 'recent'")

        # Check counts consistency
        total_results = reference_data["total_results"]
        sudan_results = reference_data["sudan_results"]
        actual_results = len(self.extract_records_from_data(reference_data))

        self.assertGreaterEqual(total_results, sudan_results, "total_results should be >= sudan_results")
        self.assertEqual(sudan_results, actual_results, "sudan_results should match actual results count")

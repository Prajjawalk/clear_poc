"""Stability tests for ReliefWeb data source using reference data."""

from typing import Any

from data_pipeline.sources.reliefweb import ReliefWeb

from .base_stability_test import BaseStabilityTest, SourceStabilityTestMixin


class TestReliefWebStability(BaseStabilityTest, SourceStabilityTestMixin):
    """Test ReliefWeb data format stability using hard-coded reference data."""

    def setUp(self):
        """Set up ReliefWeb test environment."""
        super().setUp()

        self.source_model, self.test_variable = self.create_test_source_and_variable(
            source_name="ReliefWeb - Test",
            source_class_name="ReliefWeb",
            variable_code="reliefweb_disasters",
            variable_name="ReliefWeb - Disasters",
            base_url="https://api.reliefweb.int/v2"
        )

        self.source_instance = ReliefWeb(self.source_model)

    def get_reference_data(self) -> dict[str, Any]:
        """Return hard-coded ReliefWeb reference data for disaster ID 52407."""
        return {
            "time": 19,
            "href": "https://api.reliefweb.int/v2/disasters/52407",
            "links": {
                "self": {
                    "href": "https://api.reliefweb.int/v2/disasters/52407?appname=nrc-ewas-sudan"
                }
            },
            "took": 11,
            "totalCount": 1,
            "count": 1,
            "data": [
                {
                    "id": "52407",
                    "score": 1,
                    "fields": {
                        "name": "Sudan: Floods - Jul 2025",
                        "status": "ongoing",
                        "glide": "FL-2025-000154-SDN",
                        "country": [
                            {
                                "name": "Sudan",
                                "shortname": "Sudan",
                                "iso3": "SDN"
                            }
                        ],
                        "type": [
                            {
                                "name": "Flash Flood"
                            },
                            {
                                "name": "Flood"
                            }
                        ],
                        "date": {
                            "created": "2025-07-15T00:00:00+00:00",
                            "changed": "2025-07-20T12:30:45+00:00"
                        },
                        "url": "https://reliefweb.int/disaster/fl-2025-000154-sdn",
                        "description": (
                            "Heavy rains and flooding affected multiple states across Sudan in July 2025, "
                            "causing displacement and infrastructure damage. The flooding particularly impacted "
                            "Khartoum, Blue Nile, and South Darfur states."
                        ),
                        "primary_country": {
                            "name": "Sudan",
                            "iso3": "SDN"
                        }
                    }
                }
            ]
        }

    def get_expected_record_count_range(self) -> tuple[int, int]:
        """ReliefWeb specific disaster should return exactly 1 record."""
        return (1, 1)

    def get_required_fields(self) -> dict[str, Any]:
        """Required fields for ReliefWeb disaster records."""
        return {
            "id": "52407",  # Fixed disaster ID for stable testing
            "fields": dict
        }

    def extract_records_from_data(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract disasters from ReliefWeb response structure."""
        if "data" in data:
            return data["data"]
        else:
            return []

    def validate_data_structure(self, data: dict[str, Any]):
        """Validate ReliefWeb response structure."""
        # Check top-level structure
        expected_top_level = {
            "time": int,
            "totalCount": int,
            "count": int,
            "data": list
        }
        self.assert_has_required_fields(data, expected_top_level)

        # Check data structure if records exist
        records = data["data"]
        if records:
            sample_record = records[0]
            required_fields = self.get_required_fields()
            self.assert_has_required_fields(sample_record, required_fields)

            # Check fields structure
            fields = sample_record["fields"]
            expected_fields = {
                "name": str,
                "status": str,
                "country": list,
                "type": list
            }
            self.assert_has_required_fields(fields, expected_fields)

    def test_disaster_metadata_structure(self):
        """Test that disaster metadata follows expected structure."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        disaster = records[0]
        fields = disaster["fields"]

        # Check name format
        self.assertIsInstance(fields["name"], str, "Disaster name should be string")
        self.assertIn("Sudan", fields["name"], "Disaster name should mention Sudan")
        self.assertIn("Floods", fields["name"], "Disaster name should mention floods")

        # Check status
        valid_statuses = {"ongoing", "past", "alert"}
        self.assertIn(fields["status"], valid_statuses, f"Status should be one of {valid_statuses}")

        # Check GLIDE number format
        if "glide" in fields:
            glide = fields["glide"]
            self.assertIsInstance(glide, str, "GLIDE should be string")
            self.assertIn("SDN", glide, "GLIDE should contain Sudan code")

    def test_country_information_structure(self):
        """Test that country information is properly structured."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        disaster = records[0]
        fields = disaster["fields"]

        # Check country list structure
        countries = fields["country"]
        self.assertIsInstance(countries, list, "Countries should be a list")
        self.assertGreater(len(countries), 0, "Should have at least one country")

        # Check country object structure
        sudan_country = countries[0]
        expected_country_fields = {
            "name": "Sudan",
            "iso3": "SDN"
        }
        self.assert_has_required_fields(sudan_country, expected_country_fields)

        # Check primary country if present
        if "primary_country" in fields:
            primary = fields["primary_country"]
            self.assertEqual(primary["name"], "Sudan", "Primary country should be Sudan")
            self.assertEqual(primary["iso3"], "SDN", "Primary country ISO3 should be SDN")

    def test_disaster_type_structure(self):
        """Test that disaster type information is properly structured."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        disaster = records[0]
        fields = disaster["fields"]

        # Check type list structure
        disaster_types = fields["type"]
        self.assertIsInstance(disaster_types, list, "Types should be a list")
        self.assertGreater(len(disaster_types), 0, "Should have at least one type")

        # Check type object structure
        for disaster_type in disaster_types:
            self.assertIsInstance(disaster_type, dict, "Each type should be a dict")
            self.assertIn("name", disaster_type, "Type should have name field")
            self.assertIsInstance(disaster_type["name"], str, "Type name should be string")

        # Should include flood-related types
        type_names = [dt["name"] for dt in disaster_types]
        flood_types = [name for name in type_names if "flood" in name.lower()]
        self.assertGreater(len(flood_types), 0, "Should include flood-related disaster types")

    def test_date_information_structure(self):
        """Test that date information is properly formatted."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        disaster = records[0]
        fields = disaster["fields"]

        if "date" in fields:
            date_info = fields["date"]
            self.assertIsInstance(date_info, dict, "Date should be a dict")

            # Check for common date fields
            for date_field in ["created", "changed"]:
                if date_field in date_info:
                    date_value = date_info[date_field]
                    self.assertIsInstance(date_value, str, f"{date_field} should be string")
                    # Should be ISO format with timezone
                    self.assertRegex(date_value, r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}',
                                   f"{date_field} should be ISO format with timezone")

    def test_url_and_links_structure(self):
        """Test that URL and links are properly formatted."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        disaster = records[0]
        fields = disaster["fields"]

        # Check disaster URL
        if "url" in fields:
            url = fields["url"]
            self.assertIsInstance(url, str, "URL should be string")
            self.assertTrue(url.startswith("https://"), "URL should be HTTPS")
            self.assertIn("reliefweb.int", url, "URL should be ReliefWeb domain")

        # Check top-level links
        if "links" in reference_data:
            links = reference_data["links"]
            self.assertIsInstance(links, dict, "Links should be dict")

            if "self" in links:
                self_link = links["self"]
                self.assertIn("href", self_link, "Self link should have href")
                self.assertTrue(self_link["href"].startswith("https://"), "Self link should be HTTPS")

    def test_description_content(self):
        """Test that description contains meaningful content."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        disaster = records[0]
        fields = disaster["fields"]

        if "description" in fields:
            description = fields["description"]
            self.assertIsInstance(description, str, "Description should be string")
            self.assertGreater(len(description), 20, "Description should be substantial")
            self.assertIn("Sudan", description, "Description should mention Sudan")

    def test_response_metadata(self):
        """Test that response metadata is consistent."""
        reference_data = self.get_reference_data()

        # Check response timing
        self.assertIsInstance(reference_data["time"], int, "Response time should be integer")
        self.assertIsInstance(reference_data["took"], int, "Processing time should be integer")

        # Check counts consistency
        total_count = reference_data["totalCount"]
        count = reference_data["count"]
        data_length = len(reference_data["data"])

        self.assertEqual(count, data_length, "count should match data array length")
        self.assertLessEqual(count, total_count, "count should not exceed totalCount")

        # For specific disaster, should be exactly 1
        self.assertEqual(total_count, 1, "totalCount should be 1 for specific disaster")
        self.assertEqual(count, 1, "count should be 1 for specific disaster")

    def test_disaster_id_consistency(self):
        """Test that disaster ID is consistent throughout response."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        expected_id = "52407"  # Our stable test disaster ID

        disaster = records[0]
        self.assertEqual(disaster["id"], expected_id, f"Disaster ID should be {expected_id}")

        # Check that links reference the same ID
        if "links" in reference_data and "self" in reference_data["links"]:
            self_href = reference_data["links"]["self"]["href"]
            self.assertIn(expected_id, self_href, f"Self link should reference disaster {expected_id}")

        # Check that href references the same ID
        if "href" in reference_data:
            href = reference_data["href"]
            self.assertIn(expected_id, href, f"href should reference disaster {expected_id}")

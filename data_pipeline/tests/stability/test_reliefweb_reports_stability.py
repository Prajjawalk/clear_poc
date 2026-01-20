"""Stability tests for ReliefWeb reports data source using reference data."""

from typing import Any

from data_pipeline.sources.reliefweb import ReliefWeb

from .base_stability_test import BaseStabilityTest, SourceStabilityTestMixin


class TestReliefWebReportsStability(BaseStabilityTest, SourceStabilityTestMixin):
    """Test ReliefWeb reports data format stability using hard-coded reference data."""

    def setUp(self):
        """Set up ReliefWeb reports test environment."""
        super().setUp()

        self.source_model, self.test_variable = self.create_test_source_and_variable(
            source_name="ReliefWeb Reports - Test",
            source_class_name="ReliefWeb",
            variable_code="reliefweb_reports",
            variable_name="ReliefWeb - Humanitarian Reports",
            base_url="https://api.reliefweb.int/v2"
        )

        self.source_instance = ReliefWeb(self.source_model)

    def get_reference_data(self) -> dict[str, Any]:
        """Return hard-coded ReliefWeb reports reference data."""
        return {
            "time": 24,
            "href": "https://api.reliefweb.int/v2/reports?appname=nrc-ewas-sudan",
            "links": {
                "self": {
                    "href": "https://api.reliefweb.int/v2/reports?appname=nrc-ewas-sudan&filter%5Bfield%5D=country.iso3&filter%5Bvalue%5D=SDN"
                }
            },
            "took": 18,
            "totalCount": 156,
            "count": 2,
            "data": [
                {
                    "id": "4098234",
                    "score": 1,
                    "fields": {
                        "title": "Sudan: Humanitarian Snapshot - September 2025",
                        "status": "published",
                        "format": [
                            {
                                "name": "PDF"
                            }
                        ],
                        "country": [
                            {
                                "name": "Sudan",
                                "shortname": "Sudan",
                                "iso3": "SDN"
                            }
                        ],
                        "source": [
                            {
                                "id": "1503",
                                "name": "UN Office for the Coordination of Humanitarian Affairs",
                                "shortname": "OCHA"
                            }
                        ],
                        "theme": [
                            {
                                "name": "Humanitarian Access"
                            },
                            {
                                "name": "Food and Nutrition"
                            }
                        ],
                        "date": {
                            "created": "2025-09-20T10:30:00+00:00",
                            "changed": "2025-09-20T10:30:00+00:00",
                            "original": "2025-09-18T00:00:00+00:00"
                        },
                        "url": "https://reliefweb.int/report/sudan/sudan-humanitarian-snapshot-september-2025",
                        "language": [
                            {
                                "name": "English",
                                "code": "en"
                            }
                        ],
                        "body": (
                            "The humanitarian situation in Sudan continues to deteriorate with "
                            "increasing displacement and food insecurity affecting millions. "
                            "This snapshot provides key updates on humanitarian response."
                        ),
                        "primary_country": {
                            "name": "Sudan",
                            "iso3": "SDN"
                        }
                    }
                },
                {
                    "id": "4098156",
                    "score": 0.95,
                    "fields": {
                        "title": "Sudan: Flood Response Update - August 2025",
                        "status": "published",
                        "format": [
                            {
                                "name": "HTML"
                            }
                        ],
                        "country": [
                            {
                                "name": "Sudan",
                                "shortname": "Sudan",
                                "iso3": "SDN"
                            }
                        ],
                        "source": [
                            {
                                "id": "1068",
                                "name": "International Organization for Migration",
                                "shortname": "IOM"
                            }
                        ],
                        "theme": [
                            {
                                "name": "Emergency Response"
                            },
                            {
                                "name": "Shelter and Settlements"
                            }
                        ],
                        "date": {
                            "created": "2025-08-25T14:15:00+00:00",
                            "changed": "2025-08-25T14:15:00+00:00",
                            "original": "2025-08-23T00:00:00+00:00"
                        },
                        "url": "https://reliefweb.int/report/sudan/sudan-flood-response-update-august-2025",
                        "language": [
                            {
                                "name": "English",
                                "code": "en"
                            }
                        ],
                        "body": (
                            "Severe flooding across multiple states in Sudan has displaced thousands "
                            "of families. Emergency response efforts are ongoing with focus on "
                            "shelter, clean water, and healthcare provision."
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
        """ReliefWeb reports should return 1-50 reports for Sudan."""
        return (1, 50)

    def get_required_fields(self) -> dict[str, Any]:
        """Required fields for ReliefWeb report records."""
        return {
            "id": str,
            "fields": dict
        }

    def extract_records_from_data(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract reports from ReliefWeb response structure."""
        if "data" in data:
            return data["data"]
        else:
            return []

    def validate_data_structure(self, data: dict[str, Any]):
        """Validate ReliefWeb reports response structure."""
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
                "title": str,
                "status": str,
                "country": list,
                "source": list
            }
            self.assert_has_required_fields(fields, expected_fields)

    def test_report_metadata_structure(self):
        """Test that report metadata follows expected structure."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            fields = report["fields"]

            # Check title format
            self.assertIsInstance(fields["title"], str, "Report title should be string")
            self.assertGreater(len(fields["title"]), 10, "Report title should be descriptive")
            self.assertIn("Sudan", fields["title"], "Report title should mention Sudan")

            # Check status
            valid_statuses = {"published", "draft", "embargo"}
            self.assertIn(fields["status"], valid_statuses,
                         f"Status should be one of {valid_statuses}")

            # Check format information
            if "format" in fields:
                formats = fields["format"]
                self.assertIsInstance(formats, list, "Format should be a list")
                if formats:
                    format_names = [f["name"] for f in formats]
                    valid_formats = {"PDF", "HTML", "Word", "Excel", "PowerPoint"}
                    for fmt in format_names:
                        self.assertIn(fmt, valid_formats, f"Format {fmt} should be recognized")

    def test_country_information_structure(self):
        """Test that country information is properly structured."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            fields = report["fields"]

            # Check country list structure
            countries = fields["country"]
            self.assertIsInstance(countries, list, "Countries should be a list")
            self.assertGreater(len(countries), 0, "Should have at least one country")

            # Check country object structure
            sudan_country = countries[0]  # Should be Sudan for our test
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

    def test_source_information_structure(self):
        """Test that source information is properly structured."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            fields = report["fields"]

            # Check source list structure
            sources = fields["source"]
            self.assertIsInstance(sources, list, "Sources should be a list")
            self.assertGreater(len(sources), 0, "Should have at least one source")

            # Check source object structure
            for source in sources:
                self.assertIsInstance(source, dict, "Each source should be a dict")
                self.assertIn("name", source, "Source should have name field")
                self.assertIsInstance(source["name"], str, "Source name should be string")

                # Check for shortname if present
                if "shortname" in source:
                    self.assertIsInstance(source["shortname"], str,
                                        "Source shortname should be string")

    def test_theme_classification(self):
        """Test that theme information is properly structured."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            fields = report["fields"]

            if "theme" in fields:
                themes = fields["theme"]
                self.assertIsInstance(themes, list, "Themes should be a list")

                # Check theme object structure
                for theme in themes:
                    self.assertIsInstance(theme, dict, "Each theme should be a dict")
                    self.assertIn("name", theme, "Theme should have name field")
                    self.assertIsInstance(theme["name"], str, "Theme name should be string")

                # Common humanitarian themes
                theme_names = [t["name"] for t in themes]
                common_themes = {
                    "Emergency Response", "Food and Nutrition", "Health",
                    "Humanitarian Access", "Protection", "Shelter and Settlements",
                    "Water Sanitation Hygiene"
                }

                # Should have at least one recognized theme
                has_common_theme = any(theme in common_themes for theme in theme_names)
                self.assertTrue(has_common_theme,
                              f"Should have at least one common humanitarian theme from {theme_names}")

    def test_date_information_structure(self):
        """Test that date information is properly formatted."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            fields = report["fields"]

            if "date" in fields:
                date_info = fields["date"]
                self.assertIsInstance(date_info, dict, "Date should be a dict")

                # Check for common date fields
                for date_field in ["created", "changed", "original"]:
                    if date_field in date_info:
                        date_value = date_info[date_field]
                        self.assertIsInstance(date_value, str, f"{date_field} should be string")
                        # Should be ISO format with timezone
                        self.assertRegex(
                            date_value,
                            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}',
                            f"{date_field} should be ISO format with timezone"
                        )

    def test_url_and_language_structure(self):
        """Test that URL and language information is properly formatted."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            fields = report["fields"]

            # Check report URL
            if "url" in fields:
                url = fields["url"]
                self.assertIsInstance(url, str, "URL should be string")
                self.assertTrue(url.startswith("https://"), "URL should be HTTPS")
                self.assertIn("reliefweb.int", url, "URL should be ReliefWeb domain")

            # Check language information
            if "language" in fields:
                languages = fields["language"]
                self.assertIsInstance(languages, list, "Languages should be a list")

                for language in languages:
                    self.assertIsInstance(language, dict, "Each language should be a dict")
                    self.assertIn("name", language, "Language should have name field")
                    self.assertIn("code", language, "Language should have code field")

                    # Check language codes
                    valid_codes = {"en", "fr", "es", "ar", "ru", "zh"}
                    self.assertIn(language["code"], valid_codes,
                                f"Language code {language['code']} should be recognized")

    def test_body_content_structure(self):
        """Test that report body content is meaningful."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            fields = report["fields"]

            if "body" in fields:
                body = fields["body"]
                self.assertIsInstance(body, str, "Body should be string")
                self.assertGreater(len(body), 50, "Body should be substantial content")

                # Should mention Sudan
                self.assertIn("Sudan", body, "Body should mention Sudan")

                # Should contain humanitarian-related content
                humanitarian_keywords = [
                    "humanitarian", "displacement", "response", "assistance",
                    "emergency", "crisis", "aid", "relief"
                ]
                body_lower = body.lower()
                has_humanitarian_keyword = any(
                    keyword in body_lower for keyword in humanitarian_keywords
                )
                self.assertTrue(has_humanitarian_keyword,
                              f"Body should contain humanitarian keywords: {body}")

    def test_response_metadata_consistency(self):
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

        # For reports, totalCount should be reasonable (< 10000)
        self.assertLess(total_count, 10000, "totalCount should be reasonable for reports")

    def test_report_score_structure(self):
        """Test that report relevance scores are properly structured."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            if "score" in report:
                score = report["score"]

                # Should be numeric
                self.assertIsInstance(score, (int, float), "Score should be numeric")

                # Should be reasonable relevance score (0-1 range typically)
                self.assertGreaterEqual(score, 0, "Score should be non-negative")
                self.assertLessEqual(score, 1, "Score should be <= 1 for relevance")

    def test_report_id_consistency(self):
        """Test that report IDs are properly formatted."""
        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        for report in records:
            report_id = report["id"]

            # Should be string
            self.assertIsInstance(report_id, str, "Report ID should be string")

            # Should be numeric string (ReliefWeb IDs are numeric)
            self.assertTrue(report_id.isdigit(), f"Report ID {report_id} should be numeric")

            # Should be reasonable length
            self.assertGreaterEqual(len(report_id), 6, "Report ID should be at least 6 digits")
            self.assertLessEqual(len(report_id), 10, "Report ID should be at most 10 digits")

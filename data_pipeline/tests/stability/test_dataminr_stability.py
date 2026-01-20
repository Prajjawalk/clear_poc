"""Stability tests for Dataminr data source using reference data."""

from typing import Any

from data_pipeline.sources.dataminr import Dataminr

from .base_stability_test import BaseStabilityTest, SourceStabilityTestMixin


class TestDataminrStability(BaseStabilityTest, SourceStabilityTestMixin):
    """Test Dataminr data format stability using hard-coded reference data."""

    def setUp(self):
        """Set up Dataminr test environment."""
        super().setUp()

        self.source_model, self.test_variable = self.create_test_source_and_variable(
            source_name="Dataminr - Test",
            source_class_name="Dataminr",
            variable_code="dataminr_alerts",
            variable_name="Dataminr - Real-time Alerts",
            base_url="https://firstalert-api.dataminr.com"
        )

        self.source_instance = Dataminr(self.source_model)

    def get_reference_data(self) -> dict[str, Any]:
        """Return hard-coded Dataminr reference data for historical alerts."""
        return {
            "retrieved_at": "2025-09-25T12:15:30.456789+00:00",
            "endpoint": "https://firstalert-api.dataminr.com/alerts/2/search",
            "query_params": {
                "since": "1640995200000",
                "max": 5,
                "location": "Sudan"
            },
            "auth_token_obtained": True,
            "total_alerts": 3,
            "data": {
                "alerts": [
                    {
                        "alertId": "dm_alert_12345678",
                        "expandedUrl": "https://twitter.com/user/status/1234567890",
                        "source": "twitter",
                        "alertType": {
                            "name": "Breaking News",
                            "color": "#FF0000"
                        },
                        "eventTime": "2022-01-15T08:30:00.000Z",
                        "publishedAt": "2022-01-15T08:32:15.000Z",
                        "alertText": (
                            "BREAKING: Reports of heavy fighting in North Darfur region of Sudan, "
                            "multiple casualties reported. Civilians fleeing the area."
                        ),
                        "post": {
                            "description": "Unverified reports from local sources",
                            "expandedUrl": "https://twitter.com/newsource/status/1234567890",
                            "imageUrls": [
                                "https://pbs.twimg.com/media/sample_image.jpg"
                            ]
                        },
                        "location": {
                            "name": "North Darfur, Sudan",
                            "coordinates": {
                                "latitude": 14.0285,
                                "longitude": 24.8888
                            },
                            "radius": 25000
                        },
                        "categories": [
                            {
                                "name": "Armed Conflict",
                                "id": "conflict_001"
                            },
                            {
                                "name": "Humanitarian Crisis",
                                "id": "humanitarian_001"
                            }
                        ],
                        "tags": [
                            "sudan",
                            "darfur",
                            "conflict",
                            "breaking"
                        ],
                        "watchlistId": "sudan_monitoring",
                        "caption": "Real-time conflict monitoring for Sudan",
                        "score": 85.7,
                        "userFollowersCount": 12500,
                        "related": []
                    },
                    {
                        "alertId": "dm_alert_12345679",
                        "expandedUrl": "https://reliefweb.int/updates/humanitarian-update",
                        "source": "web",
                        "alertType": {
                            "name": "Humanitarian Update",
                            "color": "#0066CC"
                        },
                        "eventTime": "2022-01-14T14:45:00.000Z",
                        "publishedAt": "2022-01-14T14:47:30.000Z",
                        "alertText": (
                            "UN reports 50,000 people displaced by floods in Blue Nile state, Sudan. "
                            "Emergency response teams deployed to affected areas."
                        ),
                        "post": {
                            "description": "Official UN humanitarian update",
                            "expandedUrl": "https://reliefweb.int/updates/sudan-flood-response"
                        },
                        "location": {
                            "name": "Blue Nile State, Sudan",
                            "coordinates": {
                                "latitude": 11.7891,
                                "longitude": 34.3592
                            },
                            "radius": 50000
                        },
                        "categories": [
                            {
                                "name": "Natural Disaster",
                                "id": "disaster_001"
                            },
                            {
                                "name": "Displacement",
                                "id": "displacement_001"
                            }
                        ],
                        "tags": [
                            "sudan",
                            "flood",
                            "displacement",
                            "humanitarian"
                        ],
                        "watchlistId": "sudan_monitoring",
                        "caption": "Flood response monitoring for Sudan",
                        "score": 92.3,
                        "userFollowersCount": None,
                        "related": [
                            "dm_alert_12345680"
                        ]
                    },
                    {
                        "alertId": "dm_alert_12345680",
                        "expandedUrl": "https://twitter.com/ngouser/status/1234567891",
                        "source": "twitter",
                        "alertType": {
                            "name": "Situational Awareness",
                            "color": "#FFA500"
                        },
                        "eventTime": "2022-01-13T16:20:00.000Z",
                        "publishedAt": "2022-01-13T16:25:45.000Z",
                        "alertText": (
                            "Local NGO reports increased food insecurity in West Darfur camps, Sudan. "
                            "Urgent need for humanitarian assistance identified."
                        ),
                        "post": {
                            "description": "NGO field report from West Darfur",
                            "expandedUrl": "https://twitter.com/ngouser/status/1234567891"
                        },
                        "location": {
                            "name": "West Darfur, Sudan",
                            "coordinates": {
                                "latitude": 13.4667,
                                "longitude": 22.6000
                            },
                            "radius": 30000
                        },
                        "categories": [
                            {
                                "name": "Food Security",
                                "id": "food_001"
                            }
                        ],
                        "tags": [
                            "sudan",
                            "darfur",
                            "food_security",
                            "humanitarian"
                        ],
                        "watchlistId": "sudan_monitoring",
                        "caption": "Food security monitoring for Sudan",
                        "score": 78.9,
                        "userFollowersCount": 3500,
                        "related": []
                    }
                ]
            }
        }

    def get_expected_record_count_range(self) -> tuple[int, int]:
        """Dataminr historical query should return 1-10 alerts."""
        return (1, 10)

    def get_required_fields(self) -> dict[str, Any]:
        """Required fields for Dataminr alert records."""
        return {
            "alertId": str,
            "alertText": str,
            "eventTime": str,
            "publishedAt": str,
            "location": dict,
            "alertType": dict,
            "source": str
        }

    def extract_records_from_data(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract alerts from Dataminr response structure."""
        if "data" in data and "alerts" in data["data"]:
            return data["data"]["alerts"]
        elif "alerts" in data:
            return data["alerts"]
        else:
            return []

    def validate_data_structure(self, data: dict[str, Any]):
        """Validate Dataminr response structure."""
        # Check top-level structure
        expected_top_level = {
            "retrieved_at": str,
            "endpoint": str,
            "total_alerts": int,
            "data": dict
        }
        self.assert_has_required_fields(data, expected_top_level)

        # Check data structure
        data_section = data["data"]
        expected_data = {
            "alerts": list
        }
        self.assert_has_required_fields(data_section, expected_data)

        # Check alerts structure if records exist
        alerts = data_section["alerts"]
        if alerts:
            sample_alert = alerts[0]
            required_fields = self.get_required_fields()
            self.assert_has_required_fields(sample_alert, required_fields)

    def test_alert_type_structure(self):
        """Test that alert type information is properly structured."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        for alert in alerts:
            alert_type = alert["alertType"]
            self.assertIsInstance(alert_type, dict, "alertType should be dict")

            # Should have name field
            self.assertIn("name", alert_type, "alertType should have name")
            self.assertIsInstance(alert_type["name"], str, "alertType name should be string")

            # Should have color field for UI display
            if "color" in alert_type:
                color = alert_type["color"]
                self.assertIsInstance(color, str, "alertType color should be string")
                self.assertTrue(color.startswith("#"), "Color should be hex format")

            # Common alert types for humanitarian monitoring
            valid_alert_types = {
                "Breaking News", "Humanitarian Update", "Situational Awareness",
                "Emergency Alert", "Weather Alert", "Security Alert"
            }
            self.assertIn(alert_type["name"], valid_alert_types,
                         f"Alert type {alert_type['name']} should be recognized")

    def test_location_data_validation(self):
        """Test that location data is properly structured and reasonable for Sudan."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        for alert in alerts:
            location = alert["location"]
            self.assertIsInstance(location, dict, "Location should be dict")

            # Should have name
            self.assertIn("name", location, "Location should have name")
            location_name = location["name"]
            self.assertIsInstance(location_name, str, "Location name should be string")
            self.assertIn("Sudan", location_name, "Location should reference Sudan")

            # Should have coordinates
            if "coordinates" in location:
                coords = location["coordinates"]
                self.assertIsInstance(coords, dict, "Coordinates should be dict")

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

            # Check radius if present
            if "radius" in location:
                radius = location["radius"]
                self.assertIsInstance(radius, int, "Radius should be integer")
                self.assertGreater(radius, 0, "Radius should be positive")
                self.assertLess(radius, 200000, "Radius should be reasonable (<200km)")

    def test_timestamp_format_consistency(self):
        """Test that timestamps are consistently formatted."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        timestamp_pattern = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z'

        for alert in alerts:
            # Check eventTime
            event_time = alert["eventTime"]
            self.assertIsInstance(event_time, str, "eventTime should be string")
            self.assertRegex(event_time, timestamp_pattern,
                           "eventTime should be ISO timestamp with milliseconds")

            # Check publishedAt
            published_at = alert["publishedAt"]
            self.assertIsInstance(published_at, str, "publishedAt should be string")
            self.assertRegex(published_at, timestamp_pattern,
                           "publishedAt should be ISO timestamp with milliseconds")

    def test_alert_text_content_quality(self):
        """Test that alert text contains meaningful information."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        for alert in alerts:
            alert_text = alert["alertText"]

            # Should be string
            self.assertIsInstance(alert_text, str, "alertText should be string")

            # Should be substantial
            self.assertGreater(len(alert_text), 20, "alertText should be descriptive")

            # Should mention Sudan
            self.assertIn("Sudan", alert_text, "alertText should mention Sudan")

            # Should contain relevant humanitarian or security keywords
            relevant_keywords = [
                "report", "conflict", "displacement", "humanitarian", "emergency",
                "flood", "drought", "crisis", "casualties", "assistance"
            ]
            alert_text_lower = alert_text.lower()
            has_relevant_keyword = any(
                keyword in alert_text_lower for keyword in relevant_keywords
            )
            self.assertTrue(has_relevant_keyword,
                          f"Alert text should contain relevant keywords: {alert_text}")

    def test_categories_and_tags_structure(self):
        """Test that categories and tags are properly structured."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        for alert in alerts:
            # Check categories if present
            if "categories" in alert:
                categories = alert["categories"]
                self.assertIsInstance(categories, list, "Categories should be list")

                for category in categories:
                    self.assertIsInstance(category, dict, "Each category should be dict")
                    self.assertIn("name", category, "Category should have name")
                    self.assertIn("id", category, "Category should have id")

                # Common humanitarian categories
                category_names = [c["name"] for c in categories]
                common_categories = {
                    "Armed Conflict", "Natural Disaster", "Humanitarian Crisis",
                    "Displacement", "Food Security", "Health Emergency"
                }
                has_common_category = any(cat in common_categories for cat in category_names)
                self.assertTrue(has_common_category,
                              "Should have at least one recognized humanitarian category")

            # Check tags if present
            if "tags" in alert:
                tags = alert["tags"]
                self.assertIsInstance(tags, list, "Tags should be list")

                for tag in tags:
                    self.assertIsInstance(tag, str, "Each tag should be string")
                    self.assertGreater(len(tag), 0, "Tag should not be empty")

                # Should have Sudan-related tag
                tags_lower = [tag.lower() for tag in tags]
                has_sudan_tag = "sudan" in tags_lower
                self.assertTrue(has_sudan_tag, "Should have Sudan-related tag")

    def test_source_information_structure(self):
        """Test that source information is properly structured."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        for alert in alerts:
            source = alert["source"]
            self.assertIsInstance(source, str, "Source should be string")

            # Common Dataminr sources
            valid_sources = {"twitter", "web", "news", "blog", "forum", "government"}
            self.assertIn(source, valid_sources, f"Source {source} should be recognized")

            # Check expanded URL if present
            if "expandedUrl" in alert:
                expanded_url = alert["expandedUrl"]
                self.assertIsInstance(expanded_url, str, "expandedUrl should be string")
                self.assertTrue(expanded_url.startswith("http"), "expandedUrl should be valid URL")

    def test_post_information_structure(self):
        """Test that post information is properly structured."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        for alert in alerts:
            if "post" in alert:
                post = alert["post"]
                self.assertIsInstance(post, dict, "Post should be dict")

                # Check description
                if "description" in post:
                    description = post["description"]
                    self.assertIsInstance(description, str, "Post description should be string")

                # Check expanded URL
                if "expandedUrl" in post:
                    expanded_url = post["expandedUrl"]
                    self.assertIsInstance(expanded_url, str, "Post expandedUrl should be string")
                    self.assertTrue(expanded_url.startswith("http"),
                                  "Post expandedUrl should be valid URL")

                # Check image URLs if present
                if "imageUrls" in post:
                    image_urls = post["imageUrls"]
                    self.assertIsInstance(image_urls, list, "imageUrls should be list")

                    for image_url in image_urls:
                        self.assertIsInstance(image_url, str, "Each imageUrl should be string")
                        self.assertTrue(image_url.startswith("http"),
                                      "Each imageUrl should be valid URL")

    def test_score_and_engagement_metrics(self):
        """Test that scoring and engagement metrics are reasonable."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        for alert in alerts:
            # Check score if present
            if "score" in alert:
                score = alert["score"]
                self.assertIsInstance(score, (int, float), "Score should be numeric")
                self.assertGreaterEqual(score, 0, "Score should be non-negative")
                self.assertLessEqual(score, 100, "Score should be <= 100")

            # Check user followers count if present (can be None)
            if "userFollowersCount" in alert:
                followers = alert["userFollowersCount"]
                if followers is not None:
                    self.assertIsInstance(followers, int, "userFollowersCount should be integer")
                    self.assertGreaterEqual(followers, 0, "userFollowersCount should be non-negative")

    def test_watchlist_and_monitoring_structure(self):
        """Test that watchlist and monitoring information is structured."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        for alert in alerts:
            # Check watchlist ID
            if "watchlistId" in alert:
                watchlist_id = alert["watchlistId"]
                self.assertIsInstance(watchlist_id, str, "watchlistId should be string")
                self.assertGreater(len(watchlist_id), 0, "watchlistId should not be empty")

            # Check caption
            if "caption" in alert:
                caption = alert["caption"]
                self.assertIsInstance(caption, str, "caption should be string")

            # Check related alerts if present
            if "related" in alert:
                related = alert["related"]
                self.assertIsInstance(related, list, "related should be list")

                for related_id in related:
                    self.assertIsInstance(related_id, str, "Each related ID should be string")

    def test_alert_id_uniqueness_and_format(self):
        """Test that alert IDs are properly formatted and unique."""
        reference_data = self.get_reference_data()
        alerts = self.extract_records_from_data(reference_data)

        alert_ids = []
        for alert in alerts:
            alert_id = alert["alertId"]

            # Should be string
            self.assertIsInstance(alert_id, str, "alertId should be string")

            # Should start with standard prefix
            self.assertTrue(alert_id.startswith("dm_alert_"),
                          f"alertId {alert_id} should start with 'dm_alert_'")

            # Should be reasonable length
            self.assertGreaterEqual(len(alert_id), 10, "alertId should be substantial length")

            alert_ids.append(alert_id)

        # All IDs should be unique
        self.assertEqual(len(alert_ids), len(set(alert_ids)), "All alert IDs should be unique")

    def test_auth_and_endpoint_metadata(self):
        """Test that authentication and endpoint metadata is consistent."""
        reference_data = self.get_reference_data()

        # Check authentication status
        auth_obtained = reference_data["auth_token_obtained"]
        self.assertIsInstance(auth_obtained, bool, "auth_token_obtained should be boolean")
        self.assertTrue(auth_obtained, "Authentication should be successful for test data")

        # Check endpoint
        endpoint = reference_data["endpoint"]
        self.assertIsInstance(endpoint, str, "endpoint should be string")
        self.assertTrue(endpoint.startswith("https://"), "endpoint should be HTTPS")
        self.assertIn("dataminr.com", endpoint, "endpoint should be Dataminr domain")

        # Check query params consistency
        query_params = reference_data["query_params"]
        self.assertIsInstance(query_params, dict, "query_params should be dict")

        if "location" in query_params:
            location = query_params["location"]
            self.assertIn("Sudan", location, "query location should reference Sudan")

        # Check total alerts consistency
        total_alerts = reference_data["total_alerts"]
        actual_alerts = len(self.extract_records_from_data(reference_data))
        self.assertEqual(total_alerts, actual_alerts,
                        "total_alerts should match actual alerts count")

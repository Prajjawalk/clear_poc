"""Dataminr FirstAlert API data source implementation."""

import json
import os
from datetime import datetime
from typing import Any, Optional

import requests
from django.utils import timezone

from ..base_source import Source
from ..models import Variable, VariableData


class Dataminr(Source):
    """Dataminr FirstAlert API source implementation.

    Retrieves real-time alerts and early warning signals from Dataminr FirstAlert API.

    The Dataminr FirstAlert API provides access to real-time breaking news and emerging
    risk intelligence from social media and other public information sources.

    Authentication flow:
    1. Use userAuthorization endpoint to get access token
    2. Use access token to retrieve alerts from alerts endpoint

    Variables:
    - dataminr_alerts: Real-time alerts with geographic location data
    """

    def __init__(self, source_model):
        """Initialize Dataminr source with metadata."""
        super().__init__(source_model)
        self.base_url = "https://firstalert-api.dataminr.com"

    def get_required_env_vars(self) -> list[str]:
        """Dataminr requires API user ID and API password."""
        return ["DATAMINR_API_USER_ID", "DATAMINR_API_PASSWORD"]

    def get_test_parameters(self) -> dict:
        """Use fixed historical time range for stable testing.

        Note: For production streaming, do not use 'since' parameter.
        Use cursor-based pagination with 'from' parameter instead.
        """
        return {
            "since": "1640995200000",  # Jan 1, 2022 00:00:00 UTC in milliseconds
            "max": 5,
            "location": "Sudan",
            "max_requests": 1  # Limit pagination for testing
        }

    def test_authentication(self) -> dict[str, Any]:
        """Test Dataminr authentication flow."""
        base_result = super().test_authentication()
        if base_result["status"] != "success":
            return base_result

        try:
            # Test actual authentication
            access_token = self.get_access_token()
            return {
                "status": "success" if access_token else "failed",
                "token_obtained": access_token is not None,
                "auth_endpoint": f"{self.base_url}/auth/1/userAuthorization"
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def get_access_token(self) -> str | None:
        """Get access token from Dataminr auth endpoint."""
        try:
            # Get credentials from environment
            api_user_id = os.getenv("DATAMINR_API_USER_ID")
            api_password = os.getenv("DATAMINR_API_PASSWORD")

            if not api_user_id or not api_password:
                self.log_error("DATAMINR_API_USER_ID or DATAMINR_API_PASSWORD environment variables not set")
                return None

            self.log_info(f"Authenticating with API User ID: {api_user_id}")

            # Make authentication request
            auth_url = f"{self.base_url}/auth/1/userAuthorization"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }
            data = {
                "grant_type": "api_key",
                "scope": "first_alert_api",
                "api_user_id": api_user_id,
                "api_password": api_password,
            }

            response = requests.post(auth_url, headers=headers, data=data, timeout=30)
            response.raise_for_status()

            auth_data = response.json()
            access_token = auth_data.get("authorizationToken")

            if access_token:
                self.log_info("Successfully obtained access token")

                # Store token using base class method
                # Dataminr returns expirationTime in milliseconds since epoch
                expiration_time = auth_data.get("expirationTime")
                if expiration_time:
                    # Convert to seconds and calculate expires_in from now
                    expiration_seconds = expiration_time / 1000
                    current_time = timezone.now().timestamp()
                    expires_in = int(expiration_seconds - current_time)
                else:
                    expires_in = 3600  # Default 1 hour

                self.store_auth_token(
                    access_token=access_token,
                    token_type="DmAuth",  # Dataminr uses DmAuth format
                    expires_in=expires_in
                )

                return access_token
            else:
                self.log_error("No access token in auth response")
                return None

        except requests.exceptions.RequestException as e:
            self.log_error("Authentication failed", error=e)
            return None
        except Exception as e:
            self.log_error("Unexpected error during authentication", error=e)
            return None

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw Dataminr alerts data for a variable using cursor-based pagination."""
        try:
            self.log_info(f"Starting Dataminr data retrieval for {variable.code}")

            # Get valid access token
            access_token = self.get_valid_access_token()
            if not access_token:
                access_token = self.get_access_token()
                if not access_token:
                    self.log_error("Failed to obtain access token")
                    return False

            # Get stored token to check token type
            token_record = self.get_auth_token()
            token_type = token_record.token_type if token_record else "DmAuth"

            # Get current alert version (spec says this increments over time)
            alert_version = self._get_current_alert_version()

            # Build API parameters
            params = {
                "alertversion": str(alert_version),
            }

            # Handle cursor-based pagination
            cursor_from = kwargs.get("from")  # For pagination
            if cursor_from:
                # URL encode the cursor as specified in the documentation
                from urllib.parse import quote
                params["from"] = quote(cursor_from)
                self.log_info(f"Using cursor pagination with from: {cursor_from[:50]}...")

            # Add optional parameters (for testing only, not for production streaming)
            if kwargs.get("since"):
                params["since"] = kwargs["since"]
            if kwargs.get("max"):
                params["max"] = kwargs["max"]
            if kwargs.get("location"):
                params["location"] = kwargs["location"]

            self.log_info(f"API parameters: {params}")

            all_alerts = []
            total_requests = 0
            max_requests = kwargs.get("max_requests", 5)  # Limit requests to prevent infinite loops

            while total_requests < max_requests:
                total_requests += 1

                # Make API request
                alerts_url = f"{self.base_url}/alerts/1/alerts"
                headers = {
                    "Authorization": f"{token_type} {access_token}",
                    "Accept": "application/json",
                }

                self.log_info(f"Request {total_requests}: {alerts_url}")
                response = requests.get(alerts_url, params=params, headers=headers, timeout=60)
                response.raise_for_status()

                # Parse response
                data = response.json()
                alerts = data.get("alerts", [])
                cursor_to = data.get("to")  # Next cursor position

                self.log_info(f"Retrieved {len(alerts)} alerts, next cursor: {cursor_to[:50] if cursor_to else 'None'}...")

                if alerts:
                    all_alerts.extend(alerts)

                # Check if we have more data
                if not cursor_to or not alerts:
                    self.log_info("No more alerts to retrieve")
                    break

                # For continuous streaming, we would store the cursor and use it in next call
                # For now, we limit to one batch unless specifically doing pagination
                if not kwargs.get("continuous_streaming", False):
                    break

                # Update cursor for next request
                from urllib.parse import quote
                params["from"] = quote(cursor_to)

            # Prepare final response data
            final_data = {
                "alerts": all_alerts,
                "total_requests": total_requests,
                "alert_version": alert_version,
                "last_cursor": data.get("to") if 'data' in locals() else None,
                "retrieved_at": timezone.now().isoformat()
            }

            self.log_info(f"Retrieved total of {len(all_alerts)} alerts in {total_requests} requests")

            # Save raw data to file
            raw_file_path = self.get_raw_data_path(variable, ".json")
            with open(raw_file_path, "w", encoding="utf-8") as f:
                json.dump(final_data, f, indent=2, ensure_ascii=False)

            self.log_info(f"Raw data saved to: {raw_file_path}")
            return True

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Token expired, clear it
                self.clear_auth_token()
                self.log_error("Authentication failed (401), cleared stored tokens")
            elif e.response.status_code == 429:
                self.log_error("Rate limit exceeded (429) - API allows 180 requests per 10 minutes")
            else:
                self.log_error(f"HTTP error {e.response.status_code}", error=e)
            return False
        except requests.exceptions.RequestException as e:
            self.log_error("Request failed", error=e)
            return False
        except Exception as e:
            self.log_error("Unexpected error during data retrieval", error=e)
            return False

    def _get_current_alert_version(self) -> int:
        """Get current alert version.

        Per API spec: Required parameter to ensure alerts are delivered as expected.
        Will increment over time. Start with 19 and increment based on API responses.

        TODO: Implement proper version tracking based on API responses.
        """
        # For now, use version 19 as specified in the documentation
        # In production, this should be stored and incremented based on API feedback
        return 19

    def process(self, variable: Variable, **_kwargs) -> bool:
        """Process raw Dataminr data into standardized format."""
        try:
            self.log_info(f"Starting data processing for {variable.code}")

            # Find the most recent raw data file
            raw_data_dir = f"raw_data/{self.source_model.name}"
            if not os.path.exists(raw_data_dir):
                self.log_error(f"Raw data directory not found: {raw_data_dir}")
                return False

            # Get the most recent file for this variable
            raw_files = [
                f for f in os.listdir(raw_data_dir)
                if f.startswith(f"{self.source_model.name}_{variable.code}_") and f.endswith(".json")
            ]

            if not raw_files:
                self.log_error(f"No raw data files found for {variable.code}")
                return False

            # Sort by filename (contains timestamp) and get the most recent
            raw_files.sort(reverse=True)
            raw_file_path = os.path.join(raw_data_dir, raw_files[0])
            self.log_info(f"Processing file: {raw_file_path}")

            # Load raw data
            with open(raw_file_path, encoding="utf-8") as f:
                raw_data = json.load(f)

            alerts = raw_data.get("alerts", [])
            if not alerts:
                self.log_info("No alerts found in raw data")
                return True

            self.log_info(f"Processing {len(alerts)} alerts")

            # Process each alert
            processed_count = 0
            for alert in alerts:
                if self._process_single_alert(variable, alert, raw_file_path):
                    processed_count += 1

            self.log_info(f"Successfully processed {processed_count} out of {len(alerts)} alerts")
            return processed_count > 0

        except Exception as e:
            self.log_error("Processing failed", error=e)
            return False

    def _process_single_alert(self, variable: Variable, alert: dict[str, Any], _raw_file_path: str) -> bool:
        """Process a single alert record with complete field extraction per API spec."""
        try:
            # Extract basic alert information
            alert_id = alert.get("alertId")
            if not alert_id:
                self.log_error("Alert missing alertId")
                return False

            # Parse event time (Unix timestamp in milliseconds)
            event_time = alert.get("eventTime")
            if not event_time:
                self.log_error(f"Alert {alert_id} missing eventTime")
                return False

            from datetime import UTC
            event_datetime = datetime.fromtimestamp(event_time / 1000, tz=UTC)

            # Extract location information
            # estimatedEventLocation is an array: [location_name, latitude, longitude, confidence_radius, grid_reference]
            location_data = alert.get("estimatedEventLocation", [])
            if not location_data or len(location_data) < 3:
                self.log_error(f"Alert {alert_id} missing location data")
                return False

            location_name = location_data[0] if len(location_data) > 0 else ""
            try:
                latitude = float(location_data[1]) if len(location_data) > 1 else None
                longitude = float(location_data[2]) if len(location_data) > 2 else None
                confidence_radius = float(location_data[3]) if len(location_data) > 3 else None
                grid_reference = location_data[4] if len(location_data) > 4 else ""
            except (ValueError, IndexError):
                self.log_error(f"Alert {alert_id} has invalid coordinate data")
                return False

            if latitude is None or longitude is None:
                self.log_error(f"Alert {alert_id} missing coordinates")
                return False

            # Extract alert type and criticality
            alert_type = alert.get("alertType", {})
            alert_criticality = alert_type.get("name", "") if isinstance(alert_type, dict) else ""

            # Extract basic text fields
            headline = alert.get("headline", "")

            # Extract subHeadline structure (per API spec)
            sub_headline = alert.get("subHeadline", {})
            sub_headline_title = ""
            sub_headline_text = ""
            if isinstance(sub_headline, dict):
                sub_headline_title = sub_headline.get("title", "")
                sub_headlines = sub_headline.get("subHeadlines", "")
                if sub_headlines:
                    sub_headline_text = sub_headlines if isinstance(sub_headlines, str) else str(sub_headlines)

            # Extract publicPost information (per API spec)
            public_post = alert.get("publicPost", {})
            public_post_link = public_post.get("link", "") if isinstance(public_post, dict) else ""
            public_post_text = public_post.get("text", "") if isinstance(public_post, dict) else ""
            public_post_translated = public_post.get("translatedText", "") if isinstance(public_post, dict) else ""
            public_post_media = public_post.get("media", []) if isinstance(public_post, dict) else []

            # Extract First Alert URL
            first_alert_url = alert.get("firstAlertURL", "")

            # Extract alert lists (categories)
            alert_lists = alert.get("alertLists", [])
            categories = [lst.get("name", "") for lst in alert_lists if lst.get("name")]
            primary_category = categories[0] if categories else ""

            # Extract alert topics
            alert_topics = alert.get("alertTopics", [])
            topics = []
            topic_ids = []
            for topic in alert_topics:
                if topic.get("name"):
                    topics.append(topic.get("name"))
                if topic.get("id"):
                    topic_ids.append(topic.get("id"))

            # Extract linked alerts (per API spec)
            linked_alerts = alert.get("linkedAlerts", [])
            parent_alert_id = ""
            linked_alert_count = 0
            if linked_alerts:
                linked_alert = linked_alerts[0] if len(linked_alerts) > 0 else {}
                parent_alert_id = linked_alert.get("parentId", "")
                linked_alert_count = linked_alert.get("count", 0)

            # Extract terms of use (compliance requirement per API spec)
            terms_of_use = alert.get("termsOfUse", "")

            # Try to match location and handle unmatched locations
            context_data = {
                "original_location": location_name,
                "event_name": f"Dataminr Alert {alert_id}",
                "record_id": alert_id,
                "additional_info": f"Category: {primary_category}, Topics: {', '.join(topics)}, Criticality: {alert_criticality}"
            }

            matched_location, unmatched_location_record = self.handle_unmatched_location(
                location_name=location_name,
                source_name="Dataminr",
                context_data=context_data
            )

            # Log match status but continue processing regardless
            if not matched_location:
                self.log_info(f"No location match found for: {location_name}, saving with unmatched location record")

            # Prepare comprehensive text content
            text_parts = []
            if headline:
                text_parts.append(f"Headline: {headline}")
            if sub_headline_title:
                text_parts.append(f"Title: {sub_headline_title}")
            if sub_headline_text:
                text_parts.append(f"Context: {sub_headline_text}")
            if public_post_text:
                text_parts.append(f"Source: {public_post_text}")
            if public_post_translated:
                text_parts.append(f"Translated: {public_post_translated}")

            text_content = " | ".join(text_parts) if text_parts else headline

            # Prepare comprehensive raw data with extracted fields
            enhanced_raw_data = {
                **alert,  # Original alert data
                # Add extracted/parsed fields for easier querying
                "_extracted_fields": {
                    "alert_criticality": alert_criticality,
                    "categories": categories,
                    "topics": topics,
                    "topic_ids": topic_ids,
                    "coordinates": {
                        "latitude": latitude,
                        "longitude": longitude,
                        "confidence_radius": confidence_radius,
                        "grid_reference": grid_reference
                    },
                    "public_post": {
                        "link": public_post_link,
                        "text": public_post_text,
                        "translated_text": public_post_translated,
                        "media_urls": public_post_media
                    },
                    "sub_headline": {
                        "title": sub_headline_title,
                        "text": sub_headline_text
                    },
                    "linked_alerts": {
                        "parent_id": parent_alert_id,
                        "count": linked_alert_count
                    },
                    "urls": {
                        "first_alert": first_alert_url,
                        "terms_of_use": terms_of_use
                    }
                }
            }

            # Determine admin level - use matched location's level or guess from location name
            if matched_location:
                adm_level = matched_location.admin_level
            else:
                # For unmatched locations, use admin level from unmatched record or guess
                from location.models import AdmLevel
                try:
                    admin_level_str = unmatched_location_record.admin_level if unmatched_location_record else ""
                    if admin_level_str.isdigit():
                        adm_level = AdmLevel.objects.get(code=admin_level_str)
                    else:
                        # Default to admin level 2 (locality) for unmatched
                        adm_level = AdmLevel.objects.get(code="2")
                except AdmLevel.DoesNotExist:
                    adm_level = AdmLevel.objects.first()  # Fallback to any level

            # Create VariableData record
            variable_data = {
                "variable": variable,
                "gid": matched_location,  # Can be None for unmatched locations
                "original_location_text": location_name,
                "start_date": event_datetime.date(),
                "end_date": event_datetime.date(),
                "period": "day",
                "adm_level": adm_level,
                "value": None,
                "text": text_content,
                "raw_data": enhanced_raw_data,  # Store complete alert JSON with extracted fields
                "unmatched_location": unmatched_location_record,  # Link to unmatched location record
                "updated_at": timezone.now(),
            }

            # Create or update the record
            # Note: For unmatched locations (gid=None), we use original_location_text as part of the unique key
            if matched_location:
                _obj, created = VariableData.objects.update_or_create(
                    variable=variable,
                    gid=matched_location,
                    start_date=event_datetime.date(),
                    end_date=event_datetime.date(),
                    defaults=variable_data
                )
            else:
                # For unmatched locations, use original_location_text to avoid duplicates
                _obj, created = VariableData.objects.update_or_create(
                    variable=variable,
                    gid=None,
                    original_location_text=location_name,
                    start_date=event_datetime.date(),
                    end_date=event_datetime.date(),
                    defaults=variable_data
                )

            action = "Created" if created else "Updated"
            match_status = "matched" if matched_location else "unmatched"
            self.log_info(f"{action} VariableData for alert {alert_id} ({alert_criticality}) at {location_name} ({match_status})")
            return True

        except Exception as e:
            self.log_error(f"Failed to process alert: {str(e)}")
            return False

    def aggregate(self, variable: Variable, **kwargs) -> bool:
        """Aggregate Dataminr alerts data."""
        # For alerts, we might want to aggregate by:
        # - Day/week/month (temporal aggregation)
        # - Administrative level (geographic aggregation)
        # - Alert category or topics

        try:
            self.log_info(f"Starting aggregation for {variable.code}")

            # Use default aggregation from base class
            # This will sum the alert counts by location and time period
            return super().aggregate(variable, **kwargs)

        except Exception as e:
            self.log_error("Aggregation failed", error=e)
            return False

    def refresh_access_token(self, _token) -> bool:
        """Refresh access token for Dataminr.

        Dataminr doesn't provide refresh tokens, so we need to get a new token.
        """
        self.log_info("Dataminr doesn't support token refresh, getting new token")
        new_token = self.get_access_token()
        return new_token is not None

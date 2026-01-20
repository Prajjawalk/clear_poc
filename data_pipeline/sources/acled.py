"""ACLED data source implementation."""

import json
import os
from datetime import datetime
from typing import Any

import requests
from django.utils import timezone

from ..base_source import Source
from ..models import Variable, VariableData


class ACLED(Source):
    """ACLED (Armed Conflict Location & Event Data Project) source implementation.

    Retrieves conflict event data from ACLED API for Sudan.

    Authentication:
    - Uses session-based authentication via login endpoint
    - Access token valid for 24 hours
    - Refresh token valid for 14 days

    API Endpoint: https://acleddata.com/api/acled/read

    Variables computed from single API query:
    - acled_total_events: Total number of conflict events
    - acled_fatalities: Total fatalities from conflict events
    - acled_battles: Number of battle/armed clash events
    - acled_violence_civilians: Number of violence against civilians events
    - acled_explosions: Number of explosion/remote violence events
    - acled_riots: Number of riot/protest events
    - acled_strategic_developments: Number of strategic development events
    """

    BASE_URL = "https://acleddata.com"
    API_ENDPOINT = f"{BASE_URL}/api/acled/read"
    LOGIN_ENDPOINT = f"{BASE_URL}/user/login"

    def __init__(self, source_model):
        """Initialize ACLED source with metadata."""
        super().__init__(source_model)
        self.session = requests.Session()

    def get_required_env_vars(self) -> list[str]:
        """ACLED requires username and API key."""
        return ["ACLED_USERNAME", "ACLED_API_KEY"]

    def get_test_parameters(self) -> dict:
        """Use fixed date for stable testing."""
        return {"start_date": "2025-09-18", "end_date": "2025-09-18"}

    def test_authentication(self) -> dict[str, Any]:
        """Test ACLED session authentication."""
        base_result = super().test_authentication()
        if base_result["status"] != "success":
            return base_result

        try:
            # Test actual login process
            success = self._authenticate()
            return {
                "status": "success" if success else "failed",
                "session_valid": success,
                "login_endpoint": self.LOGIN_ENDPOINT
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _get_credentials(self) -> tuple[str, str]:
        """Get ACLED credentials from environment."""
        username = os.getenv("ACLED_USERNAME")
        password = os.getenv("ACLED_API_KEY")

        if not username or not password:
            raise ValueError("ACLED_USERNAME and ACLED_API_KEY must be set in environment")

        return username, password

    def _authenticate(self) -> bool:
        """Authenticate with ACLED API and store persistent tokens."""
        try:
            # Check for stored valid token first
            stored_token = self.get_valid_access_token()
            if stored_token:
                # Test if stored session is still valid
                # For ACLED, we store session cookies as the "access_token"
                cookie_data = self.get_auth_token().metadata.get("cookies", {})
                if cookie_data:
                    self.session.cookies.update(cookie_data)
                    test_response = self.session.get(f"{self.API_ENDPOINT}?limit=1")
                    if test_response.status_code == 200:
                        self.log_info("Using stored ACLED session")
                        return True
                    else:
                        self.log_info(f"Stored session invalid, status: {test_response.status_code}")
                        # Clear invalid stored cookies
                        self.clear_auth_token()

            # Get credentials and authenticate
            username, password = self._get_credentials()

            self.log_info("Authenticating with ACLED API")

            # Create fresh session
            self.session = requests.Session()

            # First, get initial session cookies
            initial_response = self.session.get(self.BASE_URL)
            self.log_info(f"Initial page request status: {initial_response.status_code}")

            # Login with credentials
            login_data = {"name": username, "pass": password}

            response = self.session.post(self.LOGIN_ENDPOINT, params={"_format": "json"}, headers={"Content-Type": "application/json"}, data=json.dumps(login_data))

            self.log_info(f"Login response status: {response.status_code}")

            if response.status_code != 200:
                self.log_error(f"ACLED authentication failed with status {response.status_code}")
                try:
                    error_details = response.json() if response.content else {"error": "No response content"}
                    self.log_error(f"Response details: {error_details}")

                    # Handle specific error cases
                    if response.status_code == 403:
                        error_msg = error_details.get("message", "")
                        if "too many failed login attempts" in error_msg.lower() or "temporarily blocked" in error_msg.lower():
                            self.log_error("IP address temporarily blocked due to too many failed attempts. Wait before retrying.")
                        elif "incorrect" in error_msg.lower():
                            self.log_error("Invalid credentials. Check ACLED_USERNAME and ACLED_API_KEY in environment.")
                        else:
                            self.log_error("Access denied. Verify credentials and account status.")
                    elif response.status_code == 429:
                        self.log_error("Rate limit exceeded. Wait before making more requests.")

                except:
                    self.log_error(f"Response text: {response.text[:500]}")
                return False

            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                self.log_error(f"Failed to parse login response as JSON: {e}")
                self.log_error(f"Response content: {response.text[:500]}")
                return False

            if "current_user" not in response_data:
                self.log_error("ACLED authentication failed - no user info in response")
                self.log_error(f"Response data: {response_data}")
                return False

            # Verify we can access the API
            test_response = self.session.get(f"{self.API_ENDPOINT}?limit=1")
            if test_response.status_code != 200:
                self.log_error(f"API access test failed with status: {test_response.status_code}")
                return False

            # Store session cookies as persistent token (23 hours, less than 24h validity)
            session_cookies = dict(self.session.cookies)
            self.store_auth_token(
                access_token="acled_session",  # Placeholder - actual auth is in cookies
                expires_in=23 * 3600,  # 23 hours
                metadata={
                    "cookies": session_cookies,
                    "user": response_data["current_user"]["name"],
                    "csrf_token": response_data.get("csrf_token", ""),
                    "logout_token": response_data.get("logout_token", ""),
                },
            )

            self.log_info(f"ACLED authentication successful for user {response_data['current_user']['name']}")
            return True

        except Exception as e:
            self.log_error("ACLED authentication failed", error=e)
            return False

    def check_api_status(self) -> dict[str, Any]:
        """Check ACLED API status and authentication without caching."""
        try:
            # Test basic connectivity
            session = requests.Session()
            response = session.get(self.BASE_URL, timeout=10)

            status = {
                "base_url_accessible": response.status_code == 200,
                "base_url_status": response.status_code,
                "credentials_valid": False,
                "api_accessible": False,
                "blocked": False,
                "error_message": None,
            }

            if not status["base_url_accessible"]:
                status["error_message"] = f"Cannot access ACLED website (status: {response.status_code})"
                return status

            # Test login
            username, password = self._get_credentials()
            login_data = {"name": username, "pass": password}

            login_response = session.post(self.LOGIN_ENDPOINT, params={"_format": "json"}, headers={"Content-Type": "application/json"}, data=json.dumps(login_data), timeout=10)

            if login_response.status_code == 200:
                try:
                    login_data = login_response.json()
                    if "current_user" in login_data:
                        status["credentials_valid"] = True
                        # Test API access
                        api_response = session.get(f"{self.API_ENDPOINT}?limit=1", timeout=10)
                        status["api_accessible"] = api_response.status_code == 200
                    else:
                        status["error_message"] = "Login succeeded but no user info returned"
                except json.JSONDecodeError:
                    status["error_message"] = "Invalid JSON response from login"
            elif login_response.status_code == 403:
                try:
                    error_data = login_response.json()
                    error_msg = error_data.get("message", "")
                    if "blocked" in error_msg.lower() or "too many" in error_msg.lower():
                        status["blocked"] = True
                        status["error_message"] = "IP temporarily blocked due to failed attempts"
                    else:
                        status["error_message"] = "Access denied - check credentials"
                except:
                    status["error_message"] = "Access denied"
            else:
                status["error_message"] = f"Login failed with status {login_response.status_code}"

            return status

        except Exception as e:
            return {"base_url_accessible": False, "credentials_valid": False, "api_accessible": False, "blocked": False, "error_message": f"Connection error: {str(e)}"}

    def _fetch_sudan_data(self, start_date: str = None, end_date: str = None, **kwargs) -> list[dict[str, Any]]:
        """Fetch Sudan conflict data from ACLED API."""
        if not self._authenticate():
            raise Exception("Failed to authenticate with ACLED API")

        # If no dates specified, don't add date filter (gets all available data)
        # The ACLED API will return all data if no date filter is provided

        params = {
            "country": "Sudan",
            "_format": "json",
            "limit": 5000,  # ACLED max limit
        }

        if start_date and end_date:
            # ACLED API date range format: event_date=YYYY-MM-DD|YYYY-MM-DD&event_date_where=BETWEEN
            # See: https://acleddata.com/api-documentation/getting-started
            params["event_date"] = f"{start_date}|{end_date}"
            params["event_date_where"] = "BETWEEN"
            self.log_info(f"Using date range: {start_date} to {end_date}")
        elif kwargs.get("year"):
            params["year"] = kwargs["year"]
            self.log_info(f"Using year: {kwargs['year']}")
        else:
            self.log_info("No date filter specified - will get recent data")
            
        # Test basic API connectivity first with a recent date range
        test_params = {
            "country": "Sudan", 
            "_format": "json", 
            "limit": 1,
            "event_date": "2024-01-01|2024-01-31",
            "event_date_where": "BETWEEN"
        }
        self.log_info(f"Testing API with basic params: {test_params}")
        test_response = self.session.get(self.API_ENDPOINT, params=test_params)
        self.log_info(f"Test response status: {test_response.status_code}")
        if test_response.status_code == 200:
            test_data = test_response.json()
            if isinstance(test_data, list):
                self.log_info(f"Test returned {len(test_data)} events (direct list)")
            elif isinstance(test_data, dict):
                test_events = test_data.get("data", [])
                self.log_info(f"Test returned {len(test_events)} events (wrapped), keys: {list(test_data.keys())}")
        else:
            self.log_error(f"API test failed: {test_response.text}")
            raise Exception(f"ACLED API test failed with status {test_response.status_code}")

        all_events = []
        page = 0

        while True:
            page += 1
            current_params = {**params, "page": page}

            self.log_info(f"Fetching ACLED data page {page}", params=str(current_params))

            response = self.session.get(self.API_ENDPOINT, params=current_params)

            if response.status_code != 200:
                raise Exception(f"ACLED API request failed with status {response.status_code}: {response.text}")

            # Debug: log response info
            self.log_info(f"Response status: {response.status_code}, Content-Type: {response.headers.get('content-type')}")
            if len(response.text) < 500:
                self.log_info(f"Full response: {response.text}")
            else:
                self.log_info(f"Response size: {len(response.text)} chars, first 300 chars: {response.text[:300]}")

            data = response.json()

            # Handle different ACLED API response formats
            if isinstance(data, list):
                # Direct list of events
                events = data
                self.log_info(f"Got direct list response with {len(events)} events")
            elif isinstance(data, dict):
                # Wrapped response format
                if not data.get("success"):
                    raise Exception(f"ACLED API returned error: {data.get('error', 'Unknown error')}")
                events = data.get("data", [])
                self.log_info(f"Got wrapped response: success={data.get('success')}, data_count={len(events)}, keys={list(data.keys())}")
                
                # Debug: check if there's additional info in the response
                if not events and "count" in data:
                    self.log_info(f"API reports total count: {data.get('count')}")
                if "messages" in data:
                    self.log_info(f"API messages: {data.get('messages')}")
            else:
                raise Exception(f"Unexpected ACLED API response format: {type(data)}")
            
            self.log_info(f"Page {page} returned {len(events)} events")
            if not events:
                break

            all_events.extend(events)

            # Check if we've reached the end
            if len(events) < params["limit"]:
                break

        self.log_info(f"Retrieved {len(all_events)} ACLED events for Sudan")
        return all_events

    def get_all_variables(self, **kwargs) -> bool:
        """Retrieve raw ACLED data for all variables (single API call)."""
        try:
            self.log_info("Starting ACLED data retrieval for all variables")

            # Get incremental date parameters if not explicitly provided
            if "start_date" not in kwargs and "end_date" not in kwargs and "year" not in kwargs:
                date_params = self.get_incremental_date_params()
                
                if date_params["incremental"] and date_params['start_date']:
                    # Use incremental dates only if we have existing data
                    kwargs.update(date_params)
                    self.log_info(f"Using incremental fetch from {date_params['start_date']} to {date_params['end_date']}")
                else:
                    # For first-time download, start from 2020-01-01 to avoid South Sudan issues
                    kwargs["start_date"] = "2020-01-01"
                    kwargs["end_date"] = date_params["end_date"]
                    self.log_info("No existing ACLED data found - downloading from 2020-01-01 to present")

            # Fetch all Sudan data in one query
            events = self._fetch_sudan_data(**kwargs)

            # Save raw data for all variables (they all use the same raw data)
            variables = self.source_model.variables.all()
            saved_count = 0

            for variable in variables:
                try:
                    raw_data_path = self.get_raw_data_path(variable, suffix=".json")
                    with open(raw_data_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {"retrieved_at": timezone.now().isoformat(), "total_events": len(events), "query_params": kwargs, "events": events}, f, indent=2, ensure_ascii=False
                        )
                    saved_count += 1
                except Exception as e:
                    self.log_error(f"Failed to save raw data for {variable.code}", error=e)

            self.log_info(f"Saved {len(events)} events to {saved_count} variable files")
            return saved_count > 0

        except Exception as e:
            self.log_error("ACLED data retrieval failed for all variables", error=e)
            return False

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw ACLED data for single variable (fallback method)."""
        # For backward compatibility, delegate to get_all_variables
        # since ACLED retrieves all variables in one call anyway
        return self.get_all_variables(**kwargs)

    def process_all_variables(self, **kwargs) -> bool:
        """Process raw ACLED data into standardized format for all variables."""
        try:
            self.log_info("Starting ACLED data processing for all variables")

            # Use any variable to get the raw data path (they all have the same data)
            variables = list(self.source_model.variables.all())
            if not variables:
                self.log_error("No variables found for ACLED source")
                return False

            # Find most recent raw data file from first variable
            raw_data_path = self._get_latest_raw_data_file(variables[0])
            if not raw_data_path:
                self.log_error("No raw data file found for processing")
                return False

            # Load raw data
            with open(raw_data_path, encoding="utf-8") as f:
                raw_data = json.load(f)

            events = raw_data.get("events", [])
            if not events:
                self.log_info("No events to process")
                return True

            # Compute all variables from events in one pass
            results = self._compute_variables(events)

            # Save processed data for each variable
            total_saved = 0
            for var_code, data_points in results.items():
                var_instance = Variable.objects.filter(source=self.source_model, code=var_code).first()

                if not var_instance:
                    self.log_info(f"Skipping {var_code} - variable not found")
                    continue

                saved_count = 0
                for data_point in data_points:
                    location = self.validate_location_match(
                        data_point["location_name"],
                        "ACLED",
                        context_data={
                            "original_location": data_point.get("original_location"),
                            "record_id": data_point.get("event_id"),
                            "admin1": data_point.get("admin1"),
                            "admin2": data_point.get("admin2"),
                        },
                    )

                    # Handle unmatched locations
                    unmatched_location_record = None
                    if not location:
                        from location.models import UnmatchedLocation

                        try:
                            # Build full location hierarchy for context
                            admin1 = data_point.get("admin1", "")
                            admin2 = data_point.get("admin2", "")
                            context_hierarchy = f"Sudan > {admin1} > {admin2}" if admin2 else f"Sudan > {admin1}" if admin1 else data_point["location_name"]
                            
                            unmatched_location_record, created = UnmatchedLocation.objects.get_or_create(
                                name=data_point["location_name"],
                                source="ACLED",
                                defaults={
                                    "context": context_hierarchy,
                                    "admin_level": "2",  # ACLED data is typically locality level
                                    "code": data_point.get("event_id", ""),
                                },
                            )
                            if not created:
                                unmatched_location_record.increment_occurrence()
                        except Exception as e:
                            self.log_error(f"Failed to record unmatched location: {str(e)}")
                            unmatched_location_record = None

                    # Determine admin level
                    if location:
                        admin_level = location.admin_level
                    else:
                        # Default to admin level 2 for ACLED data (locality level)
                        from location.models import AdmLevel

                        try:
                            admin_level = AdmLevel.objects.get(code="2")  # Locality level
                        except AdmLevel.DoesNotExist:
                            admin_level = AdmLevel.objects.first()  # Fallback to any level

                    # Prepare raw data based on variable type
                    raw_data = {
                        "variable_type": var_code,
                        "aggregated_value": data_point["value"],
                        "location_context": {
                            "admin1": data_point.get("admin1"),
                            "admin2": data_point.get("admin2"),
                            "location_name": data_point["location_name"],
                            "original_location": data_point.get("original_location")
                        },
                        "events": data_point.get("specific_events", data_point.get("events", []))  # Store relevant event records
                    }

                    # Save data regardless of whether location was matched
                    VariableData.objects.update_or_create(
                        variable=var_instance,
                        start_date=data_point["start_date"],
                        end_date=data_point["end_date"],
                        gid=location,  # Can be None for unmatched locations
                        original_location_text=data_point.get("original_location", data_point["location_name"]),
                        defaults={
                            "period": data_point["period"],
                            "adm_level": admin_level,
                            "value": data_point["value"],
                            "text": data_point.get("text", ""),
                            "raw_data": raw_data,  # Store complete event data
                            "unmatched_location": unmatched_location_record,
                            "updated_at": timezone.now(),
                        },
                    )
                    saved_count += 1

                self.log_info(f"Processed {var_code}: {saved_count} data points")
                total_saved += saved_count

            self.log_info(f"Total processed and saved: {total_saved} data points across all variables")
            return total_saved > 0

        except Exception as e:
            self.log_error("ACLED data processing failed for all variables", error=e)
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process raw ACLED data for single variable (fallback method)."""
        # For backward compatibility, delegate to process_all_variables
        # since ACLED processes all variables from the same raw data
        return self.process_all_variables(**kwargs)

    def _compute_variables(self, events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Compute all ACLED variables from events data."""
        # Group events by location and date
        location_groups = {}

        for event in events:
            # Use admin2 (locality) as primary location, fallback to admin1
            location_name = event.get("admin2") or event.get("admin1") or event.get("location")
            if not location_name:
                continue

            date_str = event.get("event_date")
            if not date_str:
                continue

            # Create location-date key
            key = (location_name, date_str)

            if key not in location_groups:
                location_groups[key] = {"location_name": location_name, "date": date_str, "admin1": event.get("admin1"), "admin2": event.get("admin2"), "events": []}

            location_groups[key]["events"].append(event)

        # Compute variables for each location-date group
        results = {
            "acled_total_events": [],
            "acled_fatalities": [],
            "acled_battles": [],
            "acled_violence_civilians": [],
            "acled_explosions": [],
            "acled_riots": [],
            "acled_strategic_developments": [],
        }

        for (location_name, date_str), group in location_groups.items():
            events_list = group["events"]

            # Parse date
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            # Count events by type
            total_events = len(events_list)
            total_fatalities = sum(int(e.get("fatalities", 0)) for e in events_list)

            battles = sum(1 for e in events_list if e.get("event_type") == "Battles")
            violence_civilians = sum(1 for e in events_list if e.get("disorder_type") == "Violence against civilians")
            explosions = sum(1 for e in events_list if e.get("event_type") == "Explosions/Remote violence")
            riots = sum(1 for e in events_list if e.get("disorder_type") == "Demonstrations")
            strategic = sum(1 for e in events_list if e.get("disorder_type") == "Strategic developments")

            # Collect all notes from events for this location/date
            notes_list = [event.get("notes", "") for event in events_list if event.get("notes")]
            combined_notes = " | ".join(notes_list) if notes_list else f"ACLED conflict events for {date_str}"
            
            # Create data points
            base_data = {
                "location_name": location_name,
                "original_location": f"{group['admin1']} / {group['admin2']}" if group.get("admin2") else group["admin1"],
                "admin1": group.get("admin1"),
                "admin2": group.get("admin2"),
                "start_date": date_obj,
                "end_date": date_obj,
                "period": "day",
                "text": combined_notes,
                "events": events_list,  # Store the events for this location/date
            }

            # Add to results with specific events for each variable type
            if total_events > 0:
                results["acled_total_events"].append({**base_data, "value": total_events, "specific_events": events_list})

            if total_fatalities > 0:
                fatality_events = [e for e in events_list if int(e.get("fatalities", 0)) > 0]
                results["acled_fatalities"].append({**base_data, "value": total_fatalities, "specific_events": fatality_events})

            if battles > 0:
                battle_events = [e for e in events_list if e.get("event_type") == "Battles"]
                results["acled_battles"].append({**base_data, "value": battles, "specific_events": battle_events})

            if violence_civilians > 0:
                violence_events = [e for e in events_list if e.get("disorder_type") == "Violence against civilians"]
                results["acled_violence_civilians"].append({**base_data, "value": violence_civilians, "specific_events": violence_events})

            if explosions > 0:
                explosion_events = [e for e in events_list if e.get("event_type") == "Explosions/Remote violence"]
                results["acled_explosions"].append({**base_data, "value": explosions, "specific_events": explosion_events})

            if riots > 0:
                riot_events = [e for e in events_list if e.get("disorder_type") == "Demonstrations"]
                results["acled_riots"].append({**base_data, "value": riots, "specific_events": riot_events})

            if strategic > 0:
                strategic_events = [e for e in events_list if e.get("disorder_type") == "Strategic developments"]
                results["acled_strategic_developments"].append({**base_data, "value": strategic, "specific_events": strategic_events})

        return results

    def _get_latest_raw_data_file(self, variable: Variable) -> str:
        """Find the most recent raw data file."""
        dir_path = f"raw_data/{self.source_model.name}"
        if not os.path.exists(dir_path):
            return None

        files = [f for f in os.listdir(dir_path) if f.startswith(f"{self.source_model.name}_{variable.code}") and f.endswith(".json")]

        if not files:
            return None

        # Sort by modification time, newest first
        files.sort(key=lambda f: os.path.getmtime(os.path.join(dir_path, f)), reverse=True)
        return os.path.join(dir_path, files[0])

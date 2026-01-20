"""ReliefWeb Disasters API data source implementation."""

import json
import os

import requests
from django.utils import timezone

from ..base_source import Source
from ..models import Variable, VariableData


class ReliefWeb(Source):
    """ReliefWeb Disasters API source implementation.

    Retrieves disaster information from ReliefWeb's public API.
    Stores full disaster details as JSON in the raw_data field and
    disaster description in the text field.

    API Documentation: https://apidoc.reliefweb.int/

    Endpoint: /v2/disasters
    Parameters:
        - filter[field]: country.iso3
        - filter[value]: SDN (Sudan)
        - appname: Required app identifier
        - profile: Response profile (list, full)
        - preset: Data preset (latest, etc.)
        - limit: Number of results (max 1000)

    Variables extracted:
        - reliefweb_flood_events: Flood-specific events with details
        - reliefweb_drought_events: Drought-specific events with details
        - reliefweb_conflict_events: Conflict-related disasters with details

    Rate limits:
        - Max 1000 entries per call
        - Max 1000 API calls per day
    """

    def __init__(self, source_model):
        """Initialize ReliefWeb source with metadata."""
        super().__init__(source_model)
        self.base_url = "https://api.reliefweb.int/v2"
        self.app_name = "nrc-ewas-sudan"

    def get_required_env_vars(self) -> list[str]:
        """ReliefWeb doesn't require credentials."""
        return []

    def get_test_parameters(self) -> dict:
        """Use specific disaster ID for stable testing."""
        return {"disaster_id": "52407"}  # "Sudan: Floods - Jul 2025"

    def _fetch_disaster_details(self, disaster_id: str) -> dict | None:
        """Fetch detailed information for a specific disaster.

        Args:
            disaster_id: The disaster ID to fetch details for

        Returns:
            Dict with disaster details or None if failed
        """
        try:
            url = f"{self.base_url}/disasters/{disaster_id}"
            params = {"appname": self.app_name}
            headers = {"Accept": "application/json", "User-Agent": f"{self.app_name}/1.0"}

            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # Extract the fields from the response
                if "data" in data and len(data["data"]) > 0:
                    return data["data"][0].get("fields", {})
            return None
        except Exception as e:
            self.log_error(f"Failed to fetch details for disaster {disaster_id}: {e}")
            return None

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw disasters data from ReliefWeb API."""
        try:
            self.log_info(f"Starting ReliefWeb data retrieval for {variable.code}")

            # Build API request based on variable type
            endpoint = f"{self.base_url}/disasters"

            # Common parameters for all requests
            params = {
                "appname": self.app_name,
                "profile": "list",
                "preset": "latest",
                "limit": 1000,  # Maximum allowed
            }

            # Add Sudan filter
            params["filter[field]"] = "country.iso3"
            params["filter[value]"] = "SDN"

            # Note: ReliefWeb API doesn't support complex date filtering via URL parameters
            # Since ReliefWeb disasters are not updated frequently, we skip incremental filtering
            # and rely on post-processing to filter data by date if needed
            self.log_info("ReliefWeb: Fetching all available disasters (no incremental filtering supported)")

            # Additional filters based on variable
            if "flood" in variable.code:
                params["query[value]"] = "flood"
            elif "drought" in variable.code:
                params["query[value]"] = "drought"
            elif "conflict" in variable.code:
                params["query[value]"] = "conflict OR violence OR displacement"

            self.log_info(f"Requesting URL: {endpoint}")
            self.log_info(f"Parameters: {params}")

            # Make API request
            headers = {"Accept": "application/json", "User-Agent": f"{self.app_name}/1.0"}

            response = requests.get(endpoint, params=params, headers=headers, timeout=30)
            self.log_info(f"Response status code: {response.status_code}")
            response.raise_for_status()

            data = response.json()

            # Log response metadata
            self.log_info(f"Total count: {data.get('totalCount', 0)}")
            self.log_info(f"Retrieved: {data.get('count', 0)} records")

            # Save raw data to file
            raw_data_path = self.get_raw_data_path(variable, suffix=".json")
            with open(raw_data_path, "w") as f:
                json.dump(data, f, indent=2)

            self.log_info(f"Raw data saved to: {raw_data_path}")
            return True

        except requests.exceptions.RequestException as e:
            self.log_error(f"API request failed for {variable.code}", error=e)
            return False
        except json.JSONDecodeError as e:
            self.log_error(f"Failed to parse JSON response for {variable.code}", error=e)
            return False
        except Exception as e:
            self.log_error(f"Unexpected error retrieving data for {variable.code}", error=e)
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process raw ReliefWeb disasters data into standardized format with full details."""
        try:
            self.log_info(f"Starting ReliefWeb data processing for {variable.code}")

            # Find the most recent raw data file
            raw_data_dir = f"raw_data/{self.source_model.name}"
            raw_files = [f for f in os.listdir(raw_data_dir) if f.startswith(f"{self.source_model.name}_{variable.code}_") and f.endswith(".json")]

            if not raw_files:
                self.log_error(f"No raw data files found for {variable.code}")
                return False

            # Get the most recent file
            raw_files.sort()
            latest_file = raw_files[-1]
            raw_data_path = os.path.join(raw_data_dir, latest_file)

            self.log_info(f"Processing raw data from: {raw_data_path}")

            # Load raw data
            with open(raw_data_path) as f:
                data = json.load(f)

            disasters = data.get("data", [])

            # Apply 2020-01-01 filtering during processing (since API doesn't support date filtering)
            from datetime import datetime

            cutoff_date = datetime(2020, 1, 1).date()

            original_count = len(disasters)
            disasters = [
                d
                for d in disasters
                if d.get("fields", {}).get("date", {}).get("created") and datetime.fromisoformat(d["fields"]["date"]["created"].replace("Z", "+00:00")).date() >= cutoff_date
            ]
            self.log_info(f"Filtered {len(disasters)} disasters after {original_count} before (2020+ only)")

            # Get default admin level for country-level data
            from location.models import AdmLevel

            try:
                adm0_level = AdmLevel.objects.get(code="0")  # Country level
            except AdmLevel.DoesNotExist:
                adm0_level = AdmLevel.objects.first()  # Fallback to any level

            # Collect detailed disaster information
            disaster_details = []

            # Process based on variable type
            if variable.code == "reliefweb_flood_events":
                # Flood-related disasters
                target_disasters = [d for d in disasters if any("flood" in str(t.get("name", "")).lower() for t in d.get("fields", {}).get("type", []))]

            elif variable.code == "reliefweb_drought_events":
                # Drought-related disasters
                target_disasters = [d for d in disasters if any("drought" in str(t.get("name", "")).lower() for t in d.get("fields", {}).get("type", []))]

            elif variable.code == "reliefweb_conflict_events":
                # Conflict-related disasters
                conflict_keywords = ["conflict", "violence", "war", "armed", "displacement"]
                target_disasters = [
                    d for d in disasters if any(any(keyword in str(t.get("name", "")).lower() for keyword in conflict_keywords) for t in d.get("fields", {}).get("type", []))
                ]
            else:
                self.log_error(f"Unknown variable code: {variable.code}")
                return False

            # Fetch detailed information for each disaster
            self.log_info(f"Fetching details for {len(target_disasters)} disasters...")

            for disaster in target_disasters:
                disaster_id = disaster.get("id")
                if disaster_id:
                    # Try to fetch detailed information
                    detailed_info = self._fetch_disaster_details(disaster_id)

                    if detailed_info:
                        # Use the detailed information
                        disaster_data = {
                            "id": disaster_id,
                            "name": detailed_info.get("name", ""),
                            "status": detailed_info.get("status", ""),
                            "glide": detailed_info.get("glide", ""),
                            "type": [t.get("name", "") for t in detailed_info.get("type", [])],
                            "country": [c.get("name", "") for c in detailed_info.get("country", [])],
                            "date": detailed_info.get("date", {}),
                            "description": detailed_info.get("description", ""),
                            "url": detailed_info.get("url", ""),
                            "api_url": f"{self.base_url}/disasters/{disaster_id}?appname={self.app_name}",
                        }
                    else:
                        # Fall back to basic information from list
                        fields = disaster.get("fields", {})
                        disaster_data = {
                            "id": disaster_id,
                            "name": fields.get("name", ""),
                            "status": fields.get("status", ""),
                            "glide": fields.get("glide", ""),
                            "type": [t.get("name", "") for t in fields.get("type", [])],
                            "country": [c.get("name", "") for c in fields.get("country", [])],
                            "date": fields.get("date", {}),
                            "url": fields.get("url", ""),
                            "api_url": f"{self.base_url}/disasters/{disaster_id}?appname={self.app_name}",
                        }

                    disaster_details.append(disaster_data)

                    # Log first few disasters
                    if len(disaster_details) <= 3:
                        self.log_info(f"Processed disaster: {disaster_data['name']} ({', '.join(disaster_data['type'])})")

            # Process each disaster individually by fetching full details
            saved_count = 0

            for disaster in target_disasters:
                disaster_id = disaster.get("id")
                if not disaster_id:
                    continue

                # Fetch full disaster details from API
                detailed_info = self._fetch_disaster_details(disaster_id)
                if not detailed_info:
                    self.log_info(f"Could not fetch details for disaster {disaster_id}, using basic info")
                    detailed_info = disaster.get("fields", {})
                # Extract location information from detailed disaster data
                countries = detailed_info.get("country", [])
                if countries and isinstance(countries[0], dict):
                    location_name = countries[0].get("name", "Sudan")
                    location_shortname = countries[0].get("shortname", "")
                    location_iso3 = countries[0].get("iso3", "SDN")
                else:
                    location_name = "Sudan"
                    location_shortname = ""
                    location_iso3 = "SDN"

                # Extract date information
                disaster_date = datetime.now().date()
                if detailed_info.get("date", {}).get("created"):
                    try:
                        disaster_date = datetime.fromisoformat(detailed_info["date"]["created"].replace("Z", "+00:00")).date()
                    except (ValueError, TypeError):
                        pass

                # Try to match location using standard location matching
                location = self.validate_location_match(
                    location_name,
                    "ReliefWeb",
                    context_data={
                        "disaster_id": disaster_id,
                        "shortname": location_shortname,
                        "iso3": location_iso3,
                        "disaster_types": [t.get("name", "") for t in detailed_info.get("type", [])],
                    },
                )

                # Handle unmatched locations
                unmatched_location_record = None
                if not location:
                    from location.models import UnmatchedLocation

                    try:
                        # Build context with disaster information
                        disaster_name = detailed_info.get("name", "")
                        disaster_types = [t.get("name", "") for t in detailed_info.get("type", [])]
                        context_info = f"Country: {location_name} (Disaster: {disaster_name}, Types: {', '.join(disaster_types)})"

                        unmatched_location_record, created = UnmatchedLocation.objects.get_or_create(
                            name=location_name,
                            source="ReliefWeb",
                            defaults={
                                "context": context_info,
                                "admin_level": "0",  # Country level
                                "code": location_iso3,
                            },
                        )
                        if not created:
                            unmatched_location_record.increment_occurrence()
                    except Exception as e:
                        self.log_error(f"Failed to record unmatched location: {str(e)}")
                        unmatched_location_record = None

                # Extract description for text field
                description = detailed_info.get("description", "")
                if not description:
                    # Fallback to name if no description
                    description = detailed_info.get("name", "")

                # Save individual disaster record
                VariableData.objects.update_or_create(
                    variable=variable,
                    start_date=disaster_date,
                    end_date=disaster_date,
                    gid=location,  # Can be None for unmatched locations
                    original_location_text=location_name,
                    defaults={
                        "period": "day",
                        "adm_level": adm0_level,
                        "value": 1.0,  # Each disaster is one event
                        "text": description,  # Description from disaster details
                        "raw_data": detailed_info,  # Complete disaster details as JSON
                        "unmatched_location": unmatched_location_record,
                        "updated_at": timezone.now(),
                    },
                )
                saved_count += 1

                # Log first few disasters for debugging
                if saved_count <= 3:
                    self.log_info(f"Processed disaster: {detailed_info.get('name', 'Unknown')} in {location_name}")

            self.log_info(f"Processed {variable.code}: {saved_count} disaster records saved")

            return True

        except Exception as e:
            self.log_error(f"Failed to process data for {variable.code}", error=e)
            return False

    def aggregate(self, variable: Variable, **kwargs) -> bool:
        """Aggregate ReliefWeb data (if needed).

        ReliefWeb data is typically already at country level,
        so aggregation may not be necessary.
        """
        self.log_info(f"Aggregation not required for {variable.code} - data already at country level")
        return True

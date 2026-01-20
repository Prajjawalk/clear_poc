"""IDMC IDU data source implementation."""

import json
import os
from datetime import datetime
from typing import Any

import requests
from django.utils import timezone

from ..base_source import Source
from ..models import Variable, VariableData


class IDMCIDU(Source):
    """IDMC IDU (Internal Displacement Updates) source implementation.

    Retrieves displacement data from IDMC IDU API endpoint for Sudan.

    Smart Endpoint Selection:
    - /external-api/idus/all/ : For initial retrieval or when last data >180 days old
    - /external-api/idus/last-180-days/ : For regular updates with recent data

    Documentation: https://helix-tools-api.idmcdb.org/external-api/

    Note: The API does not support server-side filtering by country.
    All filtering must be done client-side after retrieval.

    Variables extracted:
    - idmc_idu_new_displacements: New displacements (figure field)
    - idmc_idu_conflict_displacements: Conflict-related displacements
    - idmc_idu_disaster_displacements: Disaster-related displacements

    Key fields in response:
    - figure: Number of displacements
    - displacement_type: "Conflict" or "Disaster"
    - displacement_date: Date of displacement
    - locations_name: Location description
    - event_name: Event description
    """

    BASE_URL = "https://helix-tools-api.idmcdb.org"
    API_ENDPOINT_ALL = f"{BASE_URL}/external-api/idus/all/"
    API_ENDPOINT_RECENT = f"{BASE_URL}/external-api/idus/last-180-days/"

    def __init__(self, source_model):
        """Initialize IDMC IDU source."""
        super().__init__(source_model)

    def _get_api_key(self) -> str:
        """Get IDMC API key from environment."""
        api_key = os.getenv("IDMC_API_KEY")
        if not api_key:
            raise ValueError("IDMC_API_KEY must be set in environment")
        return api_key

    def get_all_variables(self, **kwargs) -> bool:
        """Retrieve raw IDU data for all variables (single API call)."""
        try:
            self.log_info("Starting IDMC IDU data retrieval for all variables")

            # Get API key
            api_key = self._get_api_key()
            self.log_info(f"Using API key: {api_key[:5]}...")

            # Build API parameters - IDU endpoints only need client_id
            # No server-side filtering is supported
            params = {"client_id": api_key}

            # Decide which endpoint to use based on existing data
            last_data_date = self.get_last_data_date()  # Check across all variables

            if last_data_date is None:
                # No existing data - get all historical data
                endpoint = self.API_ENDPOINT_ALL
                self.log_info("No existing IDU data found - retrieving all historical data")
            else:
                # Check if last data is older than 180 days
                days_since_last = (datetime.now().date() - last_data_date).days
                if days_since_last > 180:
                    # Last data is old - get all data to catch up
                    endpoint = self.API_ENDPOINT_ALL
                    self.log_info(f"Last IDU data is {days_since_last} days old (>180) - retrieving all data")
                else:
                    # Recent data exists - just get last 180 days
                    endpoint = self.API_ENDPOINT_RECENT
                    self.log_info(f"Last IDU data is {days_since_last} days old - retrieving recent data")

            self.log_info(f"Using IDU endpoint: {endpoint}")

            # Make API request
            headers = {"Accept": "application/json", "User-Agent": "NRC-EWAS/1.0"}
            response = requests.get(endpoint, params=params, headers=headers, timeout=60)

            self.log_info(f"IDU response status: {response.status_code}")
            response.raise_for_status()

            data = response.json()

            # IDU API returns a direct list of items
            if not isinstance(data, list):
                self.log_error(f"Unexpected response format: {type(data)}")
                return False

            self.log_info(f"Total IDU records received: {len(data)}")

            # Filter for Sudan data - the API doesn't support server-side filtering
            sudan_results = [item for item in data if item.get("iso3") == "SDN" or item.get("country") == "Sudan"]

            self.log_info(f"Sudan IDU records after filtering: {len(sudan_results)}")

            if sudan_results:
                # Log sample of fields for debugging
                sample = sudan_results[0]
                self.log_info(
                    f"Sample Sudan record - Event: {sample.get('event_name')}, "
                    f"Type: {sample.get('displacement_type')}, "
                    f"Figure: {sample.get('figure')}, "
                    f"Date: {sample.get('displacement_date')}"
                )

            # Apply incremental date filtering if needed
            # Since we're using last-180-days endpoint, most data is already recent
            # But we still check for truly new data since last retrieval
            if not kwargs.get("skip_incremental_filter", False):
                date_params = self.get_incremental_date_params()

                if date_params["incremental"] and date_params["start_date"]:
                    # Filter for data newer than last retrieval
                    self.log_info(f"Applying incremental filter from {date_params['start_date']}")
                    from datetime import datetime

                    start_date = datetime.strptime(date_params["start_date"], "%Y-%m-%d").date()

                    original_count = len(sudan_results)
                    sudan_results = [
                        item for item in sudan_results if item.get("displacement_date") and datetime.strptime(item["displacement_date"], "%Y-%m-%d").date() >= start_date
                    ]
                    self.log_info(f"Incremental filter: {len(sudan_results)} new records from {original_count} total")
                else:
                    # First time retrieval - get all data from last 180 days
                    self.log_info("First IDU retrieval - using all data from last 180 days")

            # Save raw data for all IDU variables (they all use the same raw data)
            variables = self.source_model.variables.all()
            saved_count = 0

            for variable in variables:
                try:
                    raw_data_path = self.get_raw_data_path(variable, suffix=".json")
                    with open(raw_data_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "retrieved_at": timezone.now().isoformat(),
                                "endpoint_used": endpoint,
                                "endpoint_type": "all" if endpoint == self.API_ENDPOINT_ALL else "recent",
                                "last_data_date": last_data_date.isoformat() if last_data_date else None,
                                "query_params": kwargs,
                                "api_params": params,
                                "total_results": len(data),  # data is the full API response
                                "sudan_results": len(sudan_results),
                                "data": {"results": sudan_results},  # Only Sudan data
                            },
                            f,
                            indent=2,
                            ensure_ascii=False,
                        )
                    saved_count += 1
                except Exception as e:
                    self.log_error(f"Failed to save raw data for {variable.code}", error=e)

            self.log_info(f"Saved IDU data to {saved_count} variable files")
            return saved_count > 0

        except Exception as e:
            self.log_error("IDMC IDU data retrieval failed for all variables", error=e)
            return False

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve IDU data for single variable (fallback method)."""
        # For backward compatibility, delegate to get_all_variables
        # The variable parameter is not used since IDU retrieves all data at once
        _ = variable
        return self.get_all_variables(**kwargs)

    def process_all_variables(self, **kwargs) -> bool:
        """Process raw IDU data into standardized format for all variables."""
        # kwargs is not used but kept for API compatibility
        _ = kwargs
        try:
            self.log_info("Starting IDMC IDU data processing for all variables")

            # Get variables and raw data
            variables = list(self.source_model.variables.all())
            if not variables:
                self.log_error("No variables found for IDMC IDU source")
                return False

            # Find most recent raw data file
            raw_data_path = self._get_latest_raw_data_file(variables[0])
            if not raw_data_path:
                self.log_error("No raw data file found for processing")
                return False

            # Load raw data
            with open(raw_data_path, encoding="utf-8") as f:
                raw_data = json.load(f)

            data = raw_data.get("data", {})
            results = data.get("results", []) if isinstance(data, dict) else []

            if not results:
                self.log_info("No IDU results to process")
                return True

            # Process all variables from the same IDU data
            total_saved = 0
            variable_results = {}

            for variable in variables:
                variable_results[variable.code] = self._process_variable_data(variable, results)

            # Save processed data for each variable
            for variable in variables:
                data_points = variable_results.get(variable.code, [])
                saved_count = 0

                for data_point in data_points:
                    # Use pre-matched location from intelligent parsing if available
                    location = data_point.get("matched_location_object")

                    # If no pre-matched location, fall back to traditional location matching
                    if not location:
                        location = self.validate_location_match(
                            data_point["location_name"],
                            "IDMC IDU",
                            context_data={"original_location": data_point.get("original_location"), "event_name": data_point.get("event_name"), "iso3": data_point.get("iso3")},
                        )

                    # Handle unmatched locations
                    unmatched_location_record = None
                    if not location:
                        from location.models import UnmatchedLocation

                        try:
                            # Truncate long location names to fit database field
                            location_name = data_point["location_name"][:250] if len(data_point["location_name"]) > 250 else data_point["location_name"]
                            context_text = data_point.get("original_location", data_point["location_name"])
                            context_text = context_text[:250] if len(context_text) > 250 else context_text

                            unmatched_location_record, created = UnmatchedLocation.objects.get_or_create(
                                name=location_name,
                                source=self.source_model.name,
                                defaults={
                                    "context": context_text,
                                    "admin_level": data_point.get("admin_level", "1"),
                                    "code": data_point.get("iso3", ""),
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
                        # Default to admin level 1 for IDU data (state/province level)
                        from location.models import AdmLevel

                        try:
                            admin_level = AdmLevel.objects.get(code="1")  # State level
                        except AdmLevel.DoesNotExist:
                            admin_level = AdmLevel.objects.first()  # Fallback to any level

                    # Save data regardless of whether location was matched
                    VariableData.objects.update_or_create(
                        variable=variable,
                        start_date=data_point["start_date"],
                        end_date=data_point["end_date"],
                        gid=location,  # Can be None for unmatched locations
                        defaults={
                            "period": data_point["period"],
                            "adm_level": admin_level,
                            "value": data_point["value"],
                            "text": data_point.get("text", ""),
                            "original_location_text": data_point.get("original_location", data_point["location_name"]),
                            "unmatched_location": unmatched_location_record,
                            "updated_at": timezone.now(),
                        },
                    )
                    saved_count += 1

                self.log_info(f"Processed {variable.code}: {saved_count} data points")
                total_saved += saved_count

            self.log_info(f"Total IDU processing: {total_saved} data points across all variables")
            return total_saved > 0

        except Exception as e:
            self.log_error("IDMC IDU data processing failed for all variables", error=e)
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process IDU data for single variable (fallback method)."""
        # For backward compatibility, delegate to process_all_variables
        # The variable parameter is not used since IDU processes all data at once
        _ = variable
        return self.process_all_variables(**kwargs)

    # DEPRECATED: Complex parsing replaced with simple semicolon splitting
    def _parse_compound_location(self, location_name: str) -> list[dict[str, str]]:
        """Parse compound location strings into separate parts with decreasing admin levels.

        Examples:
        - "North Darfur State, Sudan" -> [{"name": "North Darfur State", "level": "1"}, {"name": "Sudan", "level": "0"}]
        - "Khartoum, Sudan" -> [{"name": "Khartoum", "level": "1"}, {"name": "Sudan", "level": "0"}]
        - "Al Fashir" -> [{"name": "Al Fashir", "level": None}]

        Returns:
            List of location parts ordered by decreasing admin level (most specific first)
        """
        if not location_name:
            return []

        # Split by comma and clean each part
        parts = [part.strip() for part in location_name.split(",")]
        if not parts:
            return []

        # If only one part, return as is
        if len(parts) == 1:
            return [{"name": parts[0], "level": None}]

        # For compound locations, assume decreasing admin levels
        parsed_parts = []

        for i, part in enumerate(parts):
            if not part:
                continue

            # Determine admin level based on position and common patterns
            admin_level = None
            part_lower = part.lower()

            # Last part is usually country (admin level 0)
            if i == len(parts) - 1:
                if any(country in part_lower for country in ["sudan", "south sudan"]):
                    admin_level = "0"
            # First parts are usually states/regions (admin level 1) or localities (admin level 2)
            elif i == 0:
                if any(keyword in part_lower for keyword in ["state", "region", "darfur"]):
                    admin_level = "1"
                else:
                    # Could be locality or city - we'll try both levels during matching
                    admin_level = "2"
            else:
                # Middle parts - likely admin level 1 or 2
                if any(keyword in part_lower for keyword in ["state", "region"]):
                    admin_level = "1"
                else:
                    admin_level = "2"

            parsed_parts.append({"name": part, "level": admin_level})

        return parsed_parts

    def _try_match_location_parts(self, location_parts: list[dict[str, str]], context_data: dict = None) -> tuple:
        """Try to match location parts in order of specificity.

        Returns:
            Tuple of (matched_location, matched_part_name, used_admin_level)
        """
        if not location_parts:
            return None, None, None

        # Try each part, starting with most specific (first in list)
        for part in location_parts:
            part_name = part["name"]
            expected_level = part["level"]

            # Update context data with admin level hint if available
            enhanced_context = (context_data or {}).copy()
            if expected_level:
                enhanced_context["expected_admin_level"] = expected_level

            # Try to match this part
            matched_location = self.validate_location_match(part_name, "IDMC IDU", context_data=enhanced_context)

            if matched_location:
                return matched_location, part_name, expected_level

        # No match found
        return None, None, None

    def _process_variable_data(self, variable: Variable, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process IDU results for a specific variable."""
        data_points = []

        for result in results:
            # Extract displacement figures based on variable type
            value = None
            if variable.code == "idmc_idu_new_displacements":
                value = result.get("figure", 0)
            elif variable.code == "idmc_idu_conflict_displacements":
                # Check if this is a conflict-related displacement
                if "conflict" in str(result.get("displacement_type", "")).lower():
                    value = result.get("figure", 0)
            elif variable.code == "idmc_idu_disaster_displacements":
                # Check if this is a disaster-related displacement
                if "disaster" in str(result.get("displacement_type", "")).lower():
                    value = result.get("figure", 0)

            if value is None or value == 0:
                continue

            # Extract location and date information
            raw_location_name = result.get("locations_name", "")
            start_date_str = result.get("displacement_date")
            end_date_str = result.get("displacement_end_date") or start_date_str

            if not raw_location_name or not start_date_str:
                continue

            # Parse dates
            try:
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00")).date()
                if end_date_str:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).date()
                else:
                    end_date = start_date
            except (ValueError, AttributeError):
                continue

            # Handle semicolon-separated multiple locations
            # Split by semicolon to create separate data points for each location
            individual_locations = [loc.strip() for loc in raw_location_name.split(";") if loc.strip()]

            # Process each individual location as a separate data point
            for individual_location in individual_locations:
                # Pass the individual location directly to the location matcher
                # without complex parsing - let the location matcher handle compound locations
                data_point = {
                    "location_name": individual_location,
                    "original_location": f"{raw_location_name} (IDU)",
                    "event_name": result.get("event_name", ""),
                    "iso3": result.get("iso3", ""),
                    "start_date": start_date,
                    "end_date": end_date,
                    "period": "event",
                    "value": float(value),
                    "text": result.get("standard_info_text", result.get("event_name", "Displacement event")),
                    # No pre-matching - let the main processing handle location matching
                    "matched_location_object": None,
                    "admin_level": None,
                }

                data_points.append(data_point)

        return data_points

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

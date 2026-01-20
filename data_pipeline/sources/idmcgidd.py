"""IDMC GIDD data source implementation."""

import json
import os
from datetime import datetime
from typing import Any

import requests
from django.utils import timezone

from ..base_source import Source
from ..models import Variable, VariableData


class IDMCGIDD(Source):
    """IDMC GIDD (Global Internal Displacement Database) source implementation.

    Retrieves displacement data from IDMC GIDD API endpoint for Sudan.

    API Endpoint: /external-api/gidd/disaggregations/disaggregation-geojson/

    Variables retrieved in single API call:
    - idmc_gidd_conflict_displacement: New displacement (conflict-induced)
    - idmc_gidd_disaster_displacement: New displacement (disaster-induced)
    - idmc_gidd_total_displacement: Total new displacement (conflict + disaster)

    Data Format: GeoJSON with displacement figures by location and cause
    """

    BASE_URL = "https://helix-tools-api.idmcdb.org"
    API_ENDPOINT = f"{BASE_URL}/external-api/gidd/disaggregations/disaggregation-geojson/"

    def __init__(self, source_model):
        """Initialize IDMC GIDD source."""
        super().__init__(source_model)

    def get_required_env_vars(self) -> list[str]:
        """IDMC GIDD requires API key."""
        return ["IDMC_API_KEY"]

    def get_test_parameters(self) -> dict:
        """Use fixed year for stable testing."""
        return {"year": 2023, "iso3__in": "SDN,AB9"}

    def test_authentication(self) -> dict[str, Any]:
        """Test IDMC API key validity with actual API call."""
        base_result = super().test_authentication()
        if base_result["status"] != "success":
            return base_result

        try:
            import requests
            api_key = self._get_api_key()

            # Test minimal API call
            params = {"client_id": api_key, "iso3__in": "SDN", "limit": 1}
            response = requests.get(self.API_ENDPOINT, params=params, timeout=10)

            return {
                "status": "success" if response.status_code == 200 else "failed",
                "status_code": response.status_code,
                "api_key_valid": response.status_code == 200,
                "api_endpoint": self.API_ENDPOINT
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _get_api_key(self) -> str:
        """Get IDMC API key from environment."""
        api_key = os.getenv("IDMC_API_KEY")
        if not api_key:
            raise ValueError("IDMC_API_KEY must be set in environment")
        return api_key

    def get_all_variables(self, **kwargs) -> bool:
        """Retrieve raw GIDD data for all variables (single API call)."""
        try:
            self.log_info("Starting IDMC GIDD data retrieval for all variables")

            # Get API key
            api_key = self._get_api_key()
            self.log_info(f"Using API key: {api_key[:5]}...")

            # Build API parameters
            params = {
                "client_id": api_key,
                "iso3__in": kwargs.get("iso3_in", "SDN,AB9"),  # Sudan and Abiey Area
            }

            # Get incremental date parameters if not explicitly provided
            if not any(k in kwargs for k in ["start_date", "end_date", "year"]):
                # Pass None to get incremental params for all variables of this source
                date_params = self.get_incremental_date_params()

                if date_params["incremental"] and date_params["start_date"]:
                    self.log_info(f"Using incremental GIDD fetch from {date_params['start_date']} to {date_params['end_date']}")
                    # GIDD uses start_date/end_date format
                    params["start_date"] = date_params["start_date"]
                    params["end_date"] = date_params["end_date"]
                else:
                    # For first-time download, start from 2020-01-01
                    params["start_date"] = "2020-01-01"
                    params["end_date"] = date_params["end_date"]
                    self.log_info("No existing GIDD data, fetching from 2020-01-01 to present")
            else:
                # Add date filtering if provided explicitly
                if kwargs.get("start_date"):
                    params["start_date"] = kwargs["start_date"]
                if kwargs.get("end_date"):
                    params["end_date"] = kwargs["end_date"]
                if kwargs.get("year"):
                    params["year"] = kwargs["year"]

            self.log_info(f"GIDD API parameters: {params}")

            # Make API request
            headers = {"Accept": "application/json", "User-Agent": "NRC-EWAS/1.0"}
            response = requests.get(self.API_ENDPOINT, params=params, headers=headers, timeout=30)

            self.log_info(f"GIDD response status: {response.status_code}")
            response.raise_for_status()

            data = response.json()

            # Save raw data for all GIDD variables (they all use the same raw data)
            variables = self.source_model.variables.all()
            saved_count = 0

            for variable in variables:
                try:
                    raw_data_path = self.get_raw_data_path(variable, suffix=".geojson")
                    with open(raw_data_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {"retrieved_at": timezone.now().isoformat(), "endpoint": "gidd", "query_params": kwargs, "api_params": params, "data": data},
                            f,
                            indent=2,
                            ensure_ascii=False,
                        )
                    saved_count += 1
                except Exception as e:
                    self.log_error(f"Failed to save raw data for {variable.code}", error=e)

            self.log_info(f"Saved GIDD data to {saved_count} variable files")
            return saved_count > 0

        except Exception as e:
            self.log_error("IDMC GIDD data retrieval failed for all variables", error=e)
            return False

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve GIDD data for single variable (fallback method)."""
        # For backward compatibility, delegate to get_all_variables
        return self.get_all_variables(**kwargs)

    def process_all_variables(self, **kwargs) -> bool:
        """Process raw GIDD data into standardized format for all variables."""
        try:
            self.log_info("Starting IDMC GIDD data processing for all variables")

            # Get variables and raw data
            variables = list(self.source_model.variables.all())
            if not variables:
                self.log_error("No variables found for IDMC GIDD source")
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
            features = data.get("features", []) if isinstance(data, dict) else []

            if not features:
                self.log_info("No GIDD features to process")
                return True

            # Process all variables from the same GeoJSON data
            total_saved = 0
            variable_results = {}

            for variable in variables:
                variable_results[variable.code] = self._process_variable_data(variable, features)

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
                            "IDMC GIDD",
                            context_data={"original_location": data_point.get("original_location"), "admin_level": data_point.get("admin_level"), "iso3": data_point.get("iso3")},
                        )

                    # Handle unmatched locations
                    unmatched_location_record = None
                    if not location:
                        from location.models import UnmatchedLocation

                        try:
                            unmatched_location_record, created = UnmatchedLocation.objects.get_or_create(
                                name=data_point["location_name"],
                                source="IDMC GIDD",
                                defaults={
                                    "context": data_point.get("original_location", data_point["location_name"]),
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
                        # Default to country level (0) for GIDD data, or try to infer from admin_level field
                        from location.models import AdmLevel

                        try:
                            admin_level = AdmLevel.objects.get(code="0")  # Country level
                        except AdmLevel.DoesNotExist:
                            admin_level = AdmLevel.objects.first()  # Fallback to any level

                    # Save data regardless of whether location was matched
                    VariableData.objects.update_or_create(
                        variable=variable,
                        start_date=data_point["start_date"],
                        end_date=data_point["end_date"],
                        gid=location,  # Can be None for unmatched locations
                        original_location_text=data_point.get("original_location", data_point["location_name"]),
                        defaults={
                            "period": data_point["period"],
                            "adm_level": admin_level,
                            "value": data_point["value"],
                            "text": data_point.get("text", ""),
                            "unmatched_location": unmatched_location_record,
                            "updated_at": timezone.now(),
                        },
                    )
                    saved_count += 1

                self.log_info(f"Processed {variable.code}: {saved_count} data points")
                total_saved += saved_count

            self.log_info(f"Total GIDD processing: {total_saved} data points across all variables")
            return total_saved > 0

        except Exception as e:
            self.log_error("IDMC GIDD data processing failed for all variables", error=e)
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process GIDD data for single variable (fallback method)."""
        # For backward compatibility, delegate to process_all_variables
        return self.process_all_variables(**kwargs)

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
            matched_location = self.validate_location_match(part_name, "IDMC GIDD", context_data=enhanced_context)

            if matched_location:
                return matched_location, part_name, expected_level

        # No match found
        return None, None, None

    def _process_variable_data(self, variable: Variable, features: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process GeoJSON features for a specific variable."""
        data_points = []

        for feature in features:
            properties = feature.get("properties", {})

            # Extract displacement figures based on variable type and figure cause
            figure_cause = properties.get("Figure cause", "").lower()
            total_figures = properties.get("Total figures", 0)

            # Skip if no figures
            if not total_figures or total_figures == 0:
                continue

            # Check if this record matches the variable we're processing
            value = None
            if variable.code == "idmc_gidd_conflict_displacement":
                if figure_cause == "conflict":
                    value = total_figures
            elif variable.code == "idmc_gidd_disaster_displacement":
                if figure_cause == "disaster":
                    value = total_figures
            elif variable.code == "idmc_gidd_total_displacement":
                # For total displacement, we accept both conflict and disaster
                if figure_cause in ["conflict", "disaster"]:
                    value = total_figures

            if value is None or value == 0:
                continue

            # Extract location and date information
            locations_name = properties.get("Locations name", [])
            if not locations_name or not isinstance(locations_name, list):
                continue

            # Use first location name if multiple
            raw_location_name = locations_name[0] if locations_name else ""
            if not raw_location_name:
                continue

            year = properties.get("Year")
            iso3 = properties.get("ISO3")
            country = properties.get("Country", "")

            if not year:
                continue

            # Create date range for the year
            try:
                start_date = datetime(year, 1, 1).date()
                end_date = datetime(year, 12, 31).date()
            except (ValueError, TypeError):
                continue

            # Parse compound location string into parts
            location_parts = self._parse_compound_location(raw_location_name)

            # Try to match location parts and get the best match
            context_data = {
                "original_location": raw_location_name,
                "admin_level": properties.get("Locations accuracy", [""])[0] if properties.get("Locations accuracy") else "",
                "iso3": iso3,
                "country": country,
            }

            matched_location, matched_part_name, used_admin_level = self._try_match_location_parts(location_parts, context_data)

            # Determine the best location name to use for storage
            # Use the matched part name if we found a match, otherwise use the full original name
            location_name_for_storage = matched_part_name if matched_part_name else raw_location_name

            data_point = {
                "location_name": location_name_for_storage,
                "original_location": f"{raw_location_name} ({country}/{iso3})",
                "admin_level": used_admin_level or (properties.get("Locations accuracy", [""])[0] if properties.get("Locations accuracy") else ""),
                "iso3": iso3,
                "start_date": start_date,
                "end_date": end_date,
                "period": "year",
                "value": float(value),
                "text": f"IDMC GIDD {figure_cause.title()} displacement for {year} in {raw_location_name}",
                # Store parsing information for debugging
                "parsed_location_parts": location_parts,
                "matched_location_object": matched_location,
                "figure_cause": figure_cause,  # Store figure cause for aggregation
            }

            data_points.append(data_point)

        # For variables that might have duplicates, aggregate values by location/date
        if variable.code in ["idmc_gidd_total_displacement", "idmc_gidd_conflict_displacement", "idmc_gidd_disaster_displacement"]:
            data_points = self._aggregate_displacement_data(data_points, variable.code)

        return data_points

    def _aggregate_displacement_data(self, data_points: list[dict[str, Any]], variable_code: str) -> list[dict[str, Any]]:
        """Aggregate displacement values by location/date to prevent duplicate key constraints.

        This handles cases where multiple records for the same location/date combination
        would violate the unique constraint in the database.
        """
        aggregated = {}

        for data_point in data_points:
            # Create unique key based on location and date
            # Handle both matched locations (objects) and unmatched locations (strings)
            if data_point["matched_location_object"]:
                location_key = data_point["matched_location_object"].id
            else:
                location_key = f"unmatched_{data_point['location_name']}"

            key = (location_key, data_point["start_date"], data_point["end_date"])

            if key in aggregated:
                # Aggregate values
                aggregated[key]["value"] += data_point["value"]
                existing_causes = aggregated[key].get("aggregated_causes", [])
                if data_point["figure_cause"] not in existing_causes:
                    existing_causes.append(data_point["figure_cause"])
                    aggregated[key]["aggregated_causes"] = existing_causes

                    # Update text to reflect aggregation for total displacement
                    if variable_code == "idmc_gidd_total_displacement":
                        causes_text = " and ".join(cause.title() for cause in sorted(existing_causes))
                        year = data_point["start_date"].year
                        location = data_point["original_location"].split(" (")[0]  # Remove country part
                        aggregated[key]["text"] = f"IDMC GIDD {causes_text} displacement for {year} in {location}"
            else:
                # First occurrence - store with figure cause for potential aggregation
                data_point_copy = data_point.copy()
                data_point_copy["aggregated_causes"] = [data_point["figure_cause"]]
                aggregated[key] = data_point_copy

        return list(aggregated.values())

    def _get_latest_raw_data_file(self, variable: Variable) -> str:
        """Find the most recent raw data file."""
        dir_path = f"raw_data/{self.source_model.name}"
        if not os.path.exists(dir_path):
            return None

        files = [f for f in os.listdir(dir_path) if f.startswith(f"{self.source_model.name}_{variable.code}") and f.endswith(".geojson")]

        if not files:
            return None

        # Sort by modification time, newest first
        files.sort(key=lambda f: os.path.getmtime(os.path.join(dir_path, f)), reverse=True)
        return os.path.join(dir_path, files[0])

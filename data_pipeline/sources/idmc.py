"""IDMC data source implementation."""

import json
import os
from datetime import datetime
from typing import Any

import requests
from django.utils import timezone

from ..base_source import Source
from ..models import Variable, VariableData


class IDMC(Source):
    """IDMC (Internal Displacement Monitoring Centre) source implementation.

    Retrieves displacement data from IDMC API for both GIDD and IDU datasets.

    Two datasets are available:
    - GIDD: Global Internal Displacement Database
        - endpoint: /external-api/gidd/disaggregations/disaggregation-geojson/
        - description: Provides granular geospatial displacement data in GeoJSON format
        - filtering: iso3__in=SDN,AB9 (Sudan and Abiey Area)
        - variables extracted from geojson features:
            - idmc_gidd_conflict_displacement: New displacement (conflict-induced)
            - idmc_gidd_disaster_displacement: New displacement (disaster-induced)
            - idmc_gidd_total_displacement: Total new displacement (conflict + disaster)

    - IDU: Internal Displacement Updates
        - endpoint: /external-api/idus/last-180-days/
        - description: https://helix-tools-api.idmcdb.org/external-api/#/IDU/idus_last_180_days_retrieve
        - variables contained:
            - idmc_idu_new_displacements: New displacements reported
            - idmc_idu_conflict_displacements: Conflict-related displacements
            - idmc_idu_disaster_displacements: Disaster-related displacements
    """

    def __init__(self, source_model):
        """Initialize IDMC source with metadata."""
        super().__init__(source_model)

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw IDMC data for a variable."""
        try:
            self.log_info(f"Starting IDMC data retrieval for {variable.code}")

            # Get API key from environment
            api_key = os.getenv("IDMC_API_KEY")
            if not api_key:
                self.log_error("IDMC_API_KEY environment variable not set")
                return False
            self.log_info(f"Using API key: {api_key[:5]}...")

            # Determine dataset and endpoint based on variable
            if variable.code.startswith("idmc_gidd_"):
                dataset = "gidd"
                endpoint = "gidd/disaggregations/disaggregation-geojson"
            elif variable.code.startswith("idmc_idu_"):
                dataset = "idu"
                endpoint = "idus/last-180-days"
            else:
                self.log_error(f"Unknown IDMC variable code: {variable.code}")
                return False
            self.log_info(f"Dataset: {dataset}, Endpoint: {endpoint}")

            # Build API parameters for IDMC Helix API
            params = {"client_id": api_key}

            # Add filtering for GIDD dataset
            if dataset == "gidd":
                # Filter for Sudan and Abiey using iso3 codes
                params["iso3__in"] = kwargs.get("iso3_in", "SDN,AB9")

                # Add date filtering if provided
                if kwargs.get("start_date"):
                    params["start_date"] = kwargs["start_date"]
                if kwargs.get("end_date"):
                    params["end_date"] = kwargs["end_date"]
                if kwargs.get("year"):
                    params["year"] = kwargs["year"]
            else:
                # IDU endpoint - country filtering doesn't work on API level
                # We retrieve global data and filter during processing for Sudan (iso3=SDN)
                pass

            self.log_info(f"API parameters: {params}")

            # Make API request
            url = f"https://helix-tools-api.idmcdb.org/external-api/{endpoint}/"
            headers = {"Accept": "application/json", "User-Agent": "NRC-EWAS/1.0"}
            self.log_info(f"Requesting URL: {url}")

            # Make API request
            self.log_info(f"Requesting URL: {url}")
            response = requests.get(url, params=params, headers=headers, timeout=30)
            self.log_info(f"Response status code: {response.status_code}")
            response.raise_for_status()

            data = response.json()

            # Handle different response formats
            if isinstance(data, dict) and data.get("type") == "FeatureCollection":
                # GeoJSON FeatureCollection (GIDD)
                all_data = data
                record_count = len(data.get("features", []))
            elif isinstance(data, list):
                # Direct list response (IDU)
                all_data = data
                record_count = len(data)
            else:
                # Paginated dictionary response (other endpoints)
                all_data = []
                results = data.get("results", data.get("data", []))
                all_data.extend(results)

                # Check for pagination
                next_url = data.get("next")
                while next_url:
                    self.log_info(f"Requesting next page: {next_url}")
                    response = requests.get(next_url, headers=headers, timeout=30)
                    response.raise_for_status()

                    data = response.json()
                    results = data.get("results", data.get("data", []))
                    all_data.extend(results)
                    next_url = data.get("next")

                record_count = len(all_data)

            # Save all collected data to a single file
            raw_data_path = self.get_raw_data_path(variable, ".json")
            self.log_info(f"Saving collected data to: {raw_data_path}")
            with open(raw_data_path, "w") as f:
                json.dump(all_data, f, indent=2)

            self.log_info(f"Successfully retrieved IDMC {dataset.upper()} data", variable=variable.code, records=record_count, file_path=raw_data_path)

            return True

        except requests.RequestException as e:
            self.log_error("Failed to retrieve IDMC data", error=e, variable=variable.code)
            if hasattr(e, "response") and e.response is not None:
                self.log_error(f"Response content: {e.response.content}")
            return False

        except Exception as e:
            self.log_error("Unexpected error during IDMC retrieval", error=e, variable=variable.code)
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process raw IDMC data into standardized format."""
        try:
            self.log_info(f"Starting IDMC data processing for {variable.code}")

            # Read raw data
            raw_data_path = self.get_raw_data_path(variable, ".json")
            with open(raw_data_path) as f:
                raw_data = json.load(f)

            # Extract records based on API response structure
            # For GIDD geojson data, extract features from the FeatureCollection
            if isinstance(raw_data, list):
                records = raw_data
            elif raw_data.get("type") == "FeatureCollection":
                # Handle geojson FeatureCollection
                records = raw_data.get("features", [])
            else:
                # Handle other formats (IDU, etc.)
                records = raw_data.get("results", raw_data.get("data", []))

            processed_count = 0

            for record in records:
                try:
                    # Process based on dataset type
                    if variable.code.startswith("idmc_gidd_"):
                        success = self._process_gidd_record(variable, record)
                    elif variable.code.startswith("idmc_idu_"):
                        success = self._process_idu_record(variable, record)
                    else:
                        continue

                    if success:
                        processed_count += 1

                except Exception as e:
                    self.log_error("Failed to process IDMC record", error=e, record_id=record.get("id"))
                    continue

            self.log_info("Successfully processed IDMC data", variable=variable.code, total_records=len(records), processed_count=processed_count)

            return processed_count > 0

        except Exception as e:
            self.log_error("Failed to process IDMC data", error=e, variable=variable.code)
            return False

    def _process_gidd_record(self, variable: Variable, record: dict[str, Any]) -> bool:
        """Process a GIDD (Global Internal Displacement Database) record from geojson format."""
        try:
            # Handle geojson feature format - data is in properties
            properties = record.get("properties", record)

            # Extract dates using Event start date and Event end date
            event_start_date_str = properties.get("Event start date", "")
            event_end_date_str = properties.get("Event end date", "")

            if event_start_date_str:
                try:
                    start_date = datetime.strptime(event_start_date_str[:10], "%Y-%m-%d").date()
                    end_date = datetime.strptime(event_end_date_str[:10], "%Y-%m-%d").date() if event_end_date_str else start_date
                except ValueError:
                    return False
            else:
                return False

            # Extract location information from geojson properties
            # Location names are in list format: ["Al Jazirah, Sudan"] or ["Abyei, أبيي, West Kurdufan, Sudan"]
            locations_name_list = properties.get("Locations name", [])

            if not locations_name_list:
                return False

            # Use first location name from the list
            location_string = locations_name_list[0]

            # Parse location string - take the first part before comma as the primary location name
            location_parts = [part.strip() for part in location_string.split(",")]
            location_name = location_parts[0] if location_parts else location_string

            # Extract admin level from Locations accuracy field
            locations_accuracy = properties.get("Locations accuracy", [])
            detected_admin_level = None
            if locations_accuracy and isinstance(locations_accuracy, list) and locations_accuracy:
                accuracy_text = locations_accuracy[0]
                # Parse admin level from accuracy text: "State/Region/Province (ADM1)" -> 1
                if "(ADM1)" in accuracy_text:
                    detected_admin_level = 1
                elif "(ADM2)" in accuracy_text:
                    detected_admin_level = 2
                elif "(ADM3)" in accuracy_text:
                    detected_admin_level = 3
                elif "(AM0)" in accuracy_text or "(ADM0)" in accuracy_text:
                    detected_admin_level = 0

            # Log admin level detection for debugging (can be removed later)
            # if detected_admin_level is not None:
            #     self.log_info(f"Detected admin level {detected_admin_level} for location: {location_name}")

            # Get displacement data from the actual field names (needed for context)
            figure_cause = properties.get("Figure cause", "")
            total_figures = properties.get("Total figures")
            figure_category = properties.get("Figure category", "")
            violence_type = properties.get("Violence type", "")
            hazard_type = properties.get("Hazard Type", "")
            year = properties.get("Year", "")

            # Match location using our gazetteer - ONLY try the primary location name
            context_data = {
                "original_location": location_string,
                "event_name": properties.get("Event name", ""),
                "record_id": properties.get("ID", ""),
                "additional_info": f"Year: {year}, Figure cause: {figure_cause}, Total figures: {total_figures}",
                "detected_admin_level": detected_admin_level,
                "locations_accuracy": locations_accuracy,
            }
            location = self.validate_location_match(location_name, "IDMC GIDD", context_data)

            # If primary location can't be matched, treat entire record as unmatched
            # No fallback to higher administrative levels - preserve specificity
            if not location:
                self.log_info("Primary location not found, preserving as unmatched", location_string=location_string, location_name=location_name)

            # Extract value based on variable type from geojson properties
            value = None
            text = ""

            if total_figures is None or total_figures <= 0:
                return False

            # Filter by variable type and figure cause
            if variable.code == "idmc_gidd_conflict_displacement":
                if "conflict" in figure_cause.lower():
                    value = float(total_figures)
                    text = f"{figure_category} - Conflict ({violence_type}) in {location_name} ({year})"
                else:
                    return False
            elif variable.code == "idmc_gidd_disaster_displacement":
                if "disaster" in figure_cause.lower():
                    value = float(total_figures)
                    text = f"{figure_category} - Disaster ({hazard_type}) in {location_name} ({year})"
                else:
                    return False
            elif variable.code == "idmc_gidd_total_displacement":
                # For total displacement, accept all causes
                value = float(total_figures)
                cause_detail = violence_type if violence_type else hazard_type
                text = f"{figure_category} - {figure_cause} ({cause_detail}) in {location_name} ({year})"
            else:
                return False

            if value is None or value <= 0:
                return False

            # Determine period based on figure category
            period = "year" if figure_category == "IDPs" else "event"

            # Create VariableData record with original location text and unmatched location reference
            # Determine admin level - use detected level from accuracy field, location's level, or default
            if location:
                admin_level = location.admin_level
                unmatched_location_ref = None  # No unmatched reference when location is found
            else:
                # For unmatched locations, use detected admin level from Locations accuracy field
                from location.models import AdmLevel

                if detected_admin_level is not None:
                    # Use the admin level detected from Locations accuracy field
                    admin_level = AdmLevel.objects.filter(code=str(detected_admin_level)).first()
                    if not admin_level:
                        # Fallback to default if the detected level doesn't exist
                        admin_level = AdmLevel.objects.filter(code="2").first() or AdmLevel.objects.first()
                        self.log_info(f"Admin level {detected_admin_level} not found, using default level 2")
                    else:
                        self.log_info(f"Using detected admin level {detected_admin_level} for unmatched location: {location_name}")
                else:
                    # Default to locality level (2) for unmatched locations when no accuracy info available
                    admin_level = AdmLevel.objects.filter(code="2").first() or AdmLevel.objects.first()
                    self.log_info("No admin level detected from accuracy field, using default level 2")

                # Get the unmatched location record that was created during validation
                unmatched_location_ref = self.get_last_unmatched_location()

            VariableData.objects.update_or_create(
                variable=variable,
                start_date=start_date,
                end_date=end_date,
                gid=location,  # Can be None for unmatched locations
                defaults={
                    "period": period,
                    "adm_level": admin_level,
                    "value": value,
                    "text": text,
                    "original_location_text": location_string,  # Store the original location string
                    "unmatched_location": unmatched_location_ref,  # Link to unmatched location record
                    "updated_at": timezone.now(),
                },
            )

            return True

        except Exception as e:
            self.log_error(
                "Failed to process GIDD record", error=e, record_id=record.get("properties", {}).get("ID"), location_data=record.get("properties", {}).get("Locations name")
            )
            return False

    def _process_idu_record(self, variable: Variable, record: dict[str, Any]) -> bool:
        """Process an IDU (Internal Displacement Updates) record."""
        try:
            # Filter for Sudan records only (since API doesn't filter properly)
            if record.get("iso3") != "SDN":
                return False

            # Extract displacement date
            date_str = record.get("displacement_date", "")
            if not date_str:
                return False

            # Parse date
            try:
                # Get start/end dates if available
                start_date_str = record.get("displacement_start_date", date_str)
                end_date_str = record.get("displacement_end_date", date_str)
                start_date = datetime.strptime(start_date_str[:10], "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date_str[:10], "%Y-%m-%d").date()
            except ValueError:
                return False

            # Extract location from locations_name field
            # Format: "Al Fasher, North Darfur State, Sudan" or "Al Jazirah, Sudan"
            locations_name = record.get("locations_name", "")
            if not locations_name:
                return False

            # Parse location string - get the primary location name (first part)
            location_parts = [part.strip() for part in locations_name.split(",")]
            location_name = location_parts[0] if location_parts else locations_name

            # Extract displacement data (needed for context)
            figure = record.get("figure", 0)
            if figure is None or figure <= 0:
                return False

            displacement_type = record.get("displacement_type", "Unknown")
            qualifier = record.get("qualifier", "")
            event_name = record.get("event_name", "")

            # Match location using our gazetteer - ONLY try the primary location name
            context_data = {
                "original_location": locations_name,
                "event_name": event_name,
                "record_id": record.get("id", ""),
                "additional_info": f"Displacement type: {displacement_type}, Figure: {figure}, Qualifier: {qualifier}",
            }
            location = self.validate_location_match(location_name, "IDMC IDU", context_data)

            # If primary location can't be matched, treat entire record as unmatched
            # No fallback to higher administrative levels - preserve specificity
            if not location:
                self.log_info("Primary location not found, preserving as unmatched", locations_name=locations_name, location_name=location_name)

            # Filter and extract value based on variable type
            value = None
            text = ""

            if variable.code == "idmc_idu_new_displacements":
                # All displacement types
                value = float(figure)
                text = f"New displacements ({displacement_type}): {event_name[:80]}..." if event_name else f"New displacements ({displacement_type}): {qualifier}"

            elif variable.code == "idmc_idu_conflict_displacements":
                # Only conflict-related displacements
                if displacement_type.lower() in ["conflict", "violence"]:
                    value = float(figure)
                    text = f"Conflict displacement: {event_name[:80]}..." if event_name else f"Conflict displacement: {qualifier}"
                else:
                    return False

            elif variable.code == "idmc_idu_disaster_displacements":
                # Only disaster-related displacements
                if displacement_type.lower() in ["disaster", "natural disaster"]:
                    value = float(figure)
                    event_detail = f"{record.get('category', '')} - {record.get('type', '')}" if record.get("category") else qualifier
                    text = f"Disaster displacement: {event_detail} - {location_name}"
                else:
                    return False
            else:
                return False

            if value is None or value <= 0:
                return False

            # Determine period based on date span
            period = "event" if start_date == end_date else "period"

            # Create VariableData record with original location text and unmatched location reference
            # Determine admin level - use location's level if available, otherwise guess from name
            if location:
                admin_level = location.admin_level
                unmatched_location_ref = None  # No unmatched reference when location is found
            else:
                # Guess admin level from location string (this is for unmatched locations)
                from location.models import AdmLevel

                # Default to locality level (2) for unmatched locations
                admin_level = AdmLevel.objects.filter(code="2").first() or AdmLevel.objects.first()
                # Get the unmatched location record that was created during validation
                unmatched_location_ref = self.get_last_unmatched_location()

            VariableData.objects.update_or_create(
                variable=variable,
                start_date=start_date,
                end_date=end_date,
                gid=location,  # Can be None for unmatched locations
                defaults={
                    "period": period,
                    "adm_level": admin_level,
                    "value": value,
                    "text": text,
                    "original_location_text": locations_name,  # Store the original location string (IDU uses locations_name)
                    "unmatched_location": unmatched_location_ref,  # Link to unmatched location record
                    "updated_at": timezone.now(),
                },
            )

            return True

        except Exception as e:
            self.log_error("Failed to process IDU record", error=e, record_id=record.get("id"), locations_name=record.get("locations_name"))
            return False

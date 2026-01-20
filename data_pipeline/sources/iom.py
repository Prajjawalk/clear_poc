"""IOM DTM data source implementation with bulk operations and caching."""

import json
import os
from datetime import datetime, timedelta

import pandas as pd
from django.db import transaction
from django.utils import timezone

from location.models import AdmLevel, Gazetteer, Location

from ..base_source import Source
from ..models import Variable, VariableData


class IOM(Source):
    """IOM (International Organization for Migration) DTM source implementation.

    Performance features:
    - Location caching for fast lookups
    - Bulk database operations
    - Transaction batching
    - Reduced database queries

    Retrieves Internal Displacement data from IOM's Displacement Tracking Matrix (DTM) API.

    Endpoint: /v3/displacement/admin2
    Parameters:
        - Admin0Pcode: SDN (Sudan)

    Variables extracted:
        - iom_dtm_displacement: Combined displacement data with IDP count in value field and reason in text field
    """

    def __init__(self, source_model):
        """Initialize IOM source with metadata."""
        super().__init__(source_model)
        self._location_cache = None
        self._adm2_level = None

    def get_required_env_vars(self) -> list[str]:
        """IOM DTM doesn't require credentials (public API)."""
        return []

    def get_test_parameters(self) -> dict:
        """Use specific admin2 pcode for stable testing."""
        return {"admin2_pcode": "SD04111"}  # Beida, West Darfur

    def _build_location_cache(self):
        """Build in-memory cache of locations for fast lookup.

        Creates a dictionary mapping pcodes and names to Location objects.
        This eliminates per-record database queries during processing.
        """
        if self._location_cache is not None:
            return  # Cache already built

        self.log_info("Building location cache for IOM processing")
        self._location_cache = {}

        # Cache all gazetteer entries for IOM_DTM
        gazetteer_entries = Gazetteer.objects.filter(source="IOM_DTM").select_related("location", "location__admin_level")

        for entry in gazetteer_entries:
            # Cache by code (pcode)
            if entry.code:
                self._location_cache[entry.code] = entry.location
            # Cache by name (lowercase for case-insensitive matching)
            if entry.name:
                self._location_cache[entry.name.lower()] = entry.location

        # Also cache direct Location lookups by geo_id
        adm2_level = AdmLevel.objects.get(code="2")
        locations = Location.objects.filter(admin_level=adm2_level).select_related("admin_level")

        for location in locations:
            if location.geo_id:
                self._location_cache[f"geo_{location.geo_id}"] = location

        self.log_info(f"Location cache built with {len(self._location_cache)} entries")

    def _lookup_location(self, admin2_pcode: str) -> Location | None:
        """Fast location lookup using cache.

        Args:
            admin2_pcode: The admin2 pcode to lookup

        Returns:
            Location object if found, None otherwise
        """
        if self._location_cache is None:
            self._build_location_cache()

        # Try direct pcode lookup
        location = self._location_cache.get(admin2_pcode)
        if location:
            return location

        # Try geo_id lookup
        location = self._location_cache.get(f"geo_{admin2_pcode}")
        if location:
            return location

        # Try lowercase name lookup
        location = self._location_cache.get(admin2_pcode.lower())
        if location:
            return location

        return None

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw IOM DTM data for a variable with incremental logic using DTM API client."""
        try:
            self.log_info(f"Starting IOM DTM data retrieval for {variable.code}")

            # Get API credentials from environment
            api_key = os.getenv("IOM_API_KEY")
            if not api_key:
                self.log_error("IOM_API_KEY environment variable not set")
                return False

            self.log_info(f"Using API key: {api_key[:5]}...")

            # Initialize DTM API client
            try:
                from dtmapi import DTMApi

                api = DTMApi(subscription_key=api_key)
            except ImportError as e:
                self.log_error(f"Failed to import DTMApi: {e}")
                return False

            # For IOM, use simple incremental logic based on the current variable's latest data
            date_params = self.get_incremental_date_params(variable)
            from_date = None
            to_date = None

            if date_params["incremental"]:
                # We have existing data - check if we need to fetch
                today = datetime.now().date()

                try:
                    last_data_date = datetime.strptime(date_params["start_date"], "%Y-%m-%d").date() - timedelta(days=1)  # Subtract 1 since start_date is day after last data
                    days_since_last = (today - last_data_date).days

                    self.log_info(f"Incremental mode: last data at {last_data_date}, {days_since_last} days ago")

                    # For IOM DTM, we should fetch if:
                    # 1. More than 7 days since last data (weekly updates typical)
                    # 2. Explicitly forced via kwargs
                    # 3. It's been more than 1 day and it's a scheduled run

                    force_fetch = kwargs.get("force_fetch", False)
                    is_scheduled = kwargs.get("scheduled", True)  # Assume scheduled unless told otherwise

                    should_fetch = (
                        force_fetch  # Always fetch if forced
                        or days_since_last >= 7  # Fetch if more than a week old
                        or (days_since_last >= 1 and is_scheduled)  # Daily scheduled fetches for recent data
                    )

                    if not should_fetch:
                        self.log_info(f"Skipping fetch: data is only {days_since_last} days old and fetch not forced")
                        return True  # Return success without fetching

                    self.log_info(f"Proceeding with incremental fetch: data is {days_since_last} days old")

                    # Set date range for incremental fetch
                    from_date = date_params["start_date"]  # This is the day after our last data
                    to_date = today.strftime("%Y-%m-%d")  # Today

                    self.log_info(f"Fetching data from {from_date} to {to_date}")

                except (ValueError, TypeError) as e:
                    self.log_info(f"Could not parse last data date ({date_params['start_date']}), proceeding with full fetch: {e}")
            else:
                self.log_info("No existing data found, performing initial fetch")

            # Fetch data using DTM API client
            try:
                self.log_info("Retrieving displacement data using DTM API client")

                # Get Admin2-level displacement data for Sudan
                if from_date and to_date:
                    self.log_info(f"Fetching incremental data from {from_date} to {to_date}")
                    data = api.get_idp_admin2_data(CountryName="Sudan", FromReportingDate=from_date, ToReportingDate=to_date)
                else:
                    self.log_info("Fetching all available data")
                    data = api.get_idp_admin2_data(CountryName="Sudan")

                # Check if data is empty (DataFrame or other types)
                if data is None or (hasattr(data, "empty") and data.empty) or (hasattr(data, "__len__") and len(data) == 0):
                    self.log_info("No data returned from DTM API")
                    return True  # Return success for empty incremental result

                # Convert DataFrame to dict/list for JSON serialization
                if hasattr(data, "to_dict"):
                    # It's a DataFrame - convert to records format
                    data = data.to_dict("records")
                    self.log_info(f"Successfully retrieved DataFrame with {len(data)} records from DTM API")
                elif hasattr(data, "__len__"):
                    self.log_info(f"Successfully retrieved {len(data)} records from DTM API")
                else:
                    self.log_info("Successfully retrieved data from DTM API (unknown format)")

            except Exception as e:
                self.log_error(f"Failed to retrieve data from DTM API: {e}")
                return False

            # For IOM, save raw data with a generic filename since both variables use the same data
            # Use a timestamp-based filename that can be shared across variables
            from datetime import datetime as dt_module

            timestamp = dt_module.now().strftime("%Y%m%d_%H%M%S")
            raw_data_filename = f"{self.source_model.name}_iom_dtm_data_{timestamp}.json"

            # Ensure the raw data directory exists
            raw_data_dir = f"raw_data/{self.source_model.name}"
            os.makedirs(raw_data_dir, exist_ok=True)

            raw_data_path = os.path.join(raw_data_dir, raw_data_filename)

            # Structure data in the expected format
            structured_data = {
                "result": data,
                "metadata": {
                    "source": "DTM API",
                    "country": "Sudan",
                    "from_date": from_date,
                    "to_date": to_date,
                    "incremental": date_params["incremental"],
                    "record_count": len(data) if data else 0,
                },
            }

            with open(raw_data_path, "w") as f:
                json.dump(structured_data, f, indent=2)

            self.log_info(f"Raw data saved to: {raw_data_path}")
            return True

        except Exception as e:
            self.log_error(f"Unexpected error retrieving data for {variable.code}", error=e)
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process raw IOM DTM data into standardized format with bulk operations."""
        try:
            self.log_info(f"Starting IOM DTM data processing for {variable.code}")

            # Build location cache
            self._build_location_cache()

            # Get admin level 2
            if self._adm2_level is None:
                self._adm2_level = AdmLevel.objects.get(code="2")

            # Find the most recent raw data file
            # Look for both variable-specific files (legacy) and shared IOM data files
            raw_data_dir = f"raw_data/{self.source_model.name}"

            # Ensure the directory exists before trying to list files
            if not os.path.exists(raw_data_dir):
                self.log_error(f"Raw data directory does not exist: {raw_data_dir}")
                return False

            # First try to find shared IOM data files (new approach)
            shared_files = [f for f in os.listdir(raw_data_dir) if f.startswith(f"{self.source_model.name}_iom_dtm_data_") and f.endswith(".json")]

            # Fallback to variable-specific files (legacy approach)
            variable_files = [f for f in os.listdir(raw_data_dir) if f.startswith(f"{self.source_model.name}_{variable.code}_") and f.endswith(".json")]

            # Use shared files if available, otherwise use variable-specific files
            raw_files = shared_files if shared_files else variable_files

            if not raw_files:
                self.log_error(f"No raw data files found for {variable.code}")
                return False

            # Get the most recent file
            raw_files.sort()
            latest_file = raw_files[-1]
            raw_data_path = os.path.join(raw_data_dir, latest_file)

            self.log_info(f"Processing IOM data from: {raw_data_path}")

            # Load raw data
            with open(raw_data_path) as f:
                data = json.load(f)

            results = data.get("result", [])
            metadata = data.get("metadata", {})

            # Check if this was an incremental fetch that legitimately returned no new data
            if not results and metadata.get("incremental", False):
                self.log_info(f"No new data to process for incremental update (API returned {metadata.get('record_count', 0)} records)")
                return True  # Success - no new data is valid for incremental updates
            elif not results:
                self.log_error(f"No results found in raw data for {variable.code}")
                return False

            # DTM API now handles date filtering at retrieval level, so no need for redundant filtering
            self.log_info(f"Processing {len(results)} records from DTM API (date filtering already applied during retrieval)")

            # Convert to DataFrame for easier processing
            df = pd.json_normalize(results)

            # Aggregate data by date and location for simplicity (matching notebook approach)
            self.log_info(f"Aggregating {len(df)} raw records by date and location")

            # Group and aggregate numeric values (sum IDPs) and take first text values
            agg_dict = {
                "numPresentIdpInd": "sum",  # Sum IDP counts for same location/date
                "admin0Name": "first",
                "admin1Name": "first",
                "admin1Pcode": "first",
                "admin2Name": "first",
                "displacementReason": "first",  # Take first reason for simplicity
            }

            df_aggregated = df.groupby(["reportingDate", "admin2Pcode"]).agg(agg_dict).reset_index()

            self.log_info(f"Aggregated to {len(df_aggregated)} unique records (date + location)")

            # Prepare bulk data
            records_to_create = []
            records_to_update = {}
            existing_records = {}

            # Get all existing records for this variable, including text field for unique key
            existing_qs = VariableData.objects.filter(variable=variable).values("start_date", "gid_id", "original_location_text", "text").distinct()

            for record in existing_qs:
                # Build key that matches the new record_key format (date + location + text)
                text_val = record.get("text", "")
                if record["gid_id"]:
                    # For matched locations, use date + location_id + text
                    key = (record["start_date"], record["gid_id"], text_val)
                else:
                    # For unmatched locations, use date + location_text + text
                    location_text = record.get("original_location_text", "")
                    key = (record["start_date"], f"unmatched_{location_text}", text_val)
                existing_records[key] = True

            self.log_info(f"Found {len(existing_records)} existing unique (date, location, displacement reason) combinations")

            processed_count = 0
            skipped_count = 0
            iteration_count = 0  # Track how many rows we actually iterate through

            # Process aggregated records and prepare for bulk operations
            for _, row in df_aggregated.iterrows():
                iteration_count += 1
                try:
                    # Extract relevant fields including full hierarchy
                    admin0_name = row.get("admin0Name", "")
                    admin1_name = row.get("admin1Name", "")
                    admin1_pcode = row.get("admin1Pcode", "")
                    admin2_name = row.get("admin2Name", "")
                    admin2_pcode = row.get("admin2Pcode")
                    reporting_date = pd.to_datetime(row.get("reportingDate"))
                    idps_present = row.get("numPresentIdpInd", 0)
                    displacement_reason = row.get("displacementReason", "")

                    if not admin2_pcode:
                        skipped_count += 1
                        continue

                    # Build full location hierarchy text
                    original_location_text = f"{admin0_name}, {admin1_name}, {admin2_name}"

                    # Try multiple matching strategies
                    location = None

                    # 1. First try pcode lookup
                    location = self._lookup_location(admin2_pcode)

                    # 2. If pcode fails, try matching by name
                    if not location and admin2_name:
                        # Try to match using the location matcher with hierarchy context
                        context_data = {
                            "original_location": original_location_text,
                            "admin0_name": admin0_name,
                            "admin1_name": admin1_name,
                            "admin1_pcode": admin1_pcode,
                            "admin2_name": admin2_name,
                            "admin2_pcode": admin2_pcode,
                            "source": "IOM_DTM",
                        }
                        location = self.validate_location_match(admin2_name, "IOM_DTM", context_data)

                    if not location:
                        if skipped_count < 10:  # Only log first few misses
                            self.log_info(f"No location match for {admin2_name} (pcode: {admin2_pcode}), saving with full context")
                        # Don't skip - save with null location for later processing
                        # Record unmatched location for manual review with full context
                        from location.models import UnmatchedLocation

                        try:
                            # Use admin2_name as primary identifier if available, otherwise pcode
                            location_identifier = admin2_name if admin2_name else admin2_pcode

                            unmatched_location_record, created = UnmatchedLocation.objects.get_or_create(
                                name=location_identifier,
                                source="IOM_DTM",
                                defaults={
                                    "context": f"Admin hierarchy: {admin0_name} > {admin1_name} > {admin2_name}",
                                    "admin_level": "2",  # Admin2 level
                                    "code": admin2_pcode,
                                    "original_location_text": original_location_text,
                                },
                            )
                            if not created:
                                unmatched_location_record.increment_occurrence()
                                # Update context if it has changed
                                if unmatched_location_record.original_location_text != original_location_text:
                                    unmatched_location_record.original_location_text = original_location_text
                                    unmatched_location_record.context = f"Admin hierarchy: {admin0_name} > {admin1_name} > {admin2_name}"
                                    unmatched_location_record.save(update_fields=["original_location_text", "context"])
                        except Exception as e:
                            self.log_error(f"Failed to record unmatched location: {str(e)}")
                            unmatched_location_record = None
                    else:
                        unmatched_location_record = None  # Location found, no unmatched record needed

                    # Store both numeric value (IDP count) and text value (displacement reason)
                    # Handle numeric conversion safely
                    try:
                        if pd.isna(idps_present) or idps_present is None:
                            value = 0
                        else:
                            value = float(idps_present)
                    except (ValueError, TypeError):
                        value = 0
                        if skipped_count < 10:  # Only log first few errors
                            self.log_info(f"Non-numeric IDP value encountered: {repr(idps_present)}, setting to 0")

                    # Store displacement reason in text field
                    text_value = str(displacement_reason) if displacement_reason else "Unknown"

                    # Check if record exists - use date + location + displacement reason for unique key
                    # This allows multiple displacement reasons per location per date
                    if location:
                        record_key = (reporting_date.date(), location.id, text_value)
                    else:
                        # For unmatched locations, use the full location text as part of the key
                        record_key = (reporting_date.date(), f"unmatched_{original_location_text}", text_value)

                    # Determine admin level - use location's level if available, otherwise use cached level
                    if location:
                        admin_level = location.admin_level
                    else:
                        admin_level = self._adm2_level or AdmLevel.objects.get(code="2")

                    # Convert pandas Series to dictionary for raw_data storage
                    # Replace NaN values with None for valid JSON
                    raw_record = row.to_dict()
                    # Clean NaN values from the dictionary
                    for key, val in raw_record.items():
                        if pd.isna(val):
                            raw_record[key] = None

                    record_data = {
                        "variable": variable,
                        "start_date": reporting_date.date(),
                        "end_date": reporting_date.date(),
                        "gid": location,  # Can be None for unmatched locations
                        "period": "day",
                        "adm_level": admin_level,
                        "value": value,  # Numeric value (None for textual variables)
                        "text": text_value,  # Text value (empty for numeric variables)
                        "raw_data": raw_record,  # Store complete IOM DTM record
                        "original_location_text": original_location_text,  # Store the full hierarchy
                        "unmatched_location": unmatched_location_record,  # Link to unmatched location record
                        "updated_at": timezone.now(),
                    }

                    if record_key not in existing_records:
                        # New record - add to create list
                        records_to_create.append(VariableData(**record_data))
                    else:
                        # Existing record - add to update dict
                        records_to_update[record_key] = record_data

                    processed_count += 1

                except Exception as e:
                    if skipped_count < 10:  # Only log first few errors
                        self.log_error(f"Error processing record: {str(e)}")
                    skipped_count += 1
                    continue

            # Perform bulk database operations within transaction
            with transaction.atomic():
                # Bulk create new records
                if records_to_create:
                    batch_size = 1000  # Process in batches to avoid memory issues
                    for i in range(0, len(records_to_create), batch_size):
                        batch = records_to_create[i : i + batch_size]
                        VariableData.objects.bulk_create(batch, ignore_conflicts=True)
                        self.log_info(f"Bulk created batch {i // batch_size + 1} ({len(batch)} records)")

                # Bulk update existing records
                if records_to_update:
                    # For updates, we need to do this more carefully
                    # Django doesn't have a direct bulk_update for our use case
                    # So we'll use update_or_create but in batches
                    update_count = 0
                    for (start_date, key_id, text_value), record_data in records_to_update.items():
                        # Handle both matched and unmatched locations
                        if isinstance(key_id, str) and key_id.startswith("unmatched_"):
                            # For unmatched locations, use original_location_text to find records
                            original_text = record_data["original_location_text"]
                            VariableData.objects.filter(
                                variable=variable,
                                start_date=start_date,
                                original_location_text=original_text,
                                text=text_value,
                                gid__isnull=True,  # Ensure we're updating unmatched records
                            ).update(
                                end_date=record_data["end_date"],
                                period=record_data["period"],
                                adm_level=record_data["adm_level"],
                                value=record_data["value"],
                                text=record_data["text"],
                                raw_data=record_data["raw_data"],
                                unmatched_location=record_data["unmatched_location"],
                                updated_at=record_data["updated_at"],
                            )
                        else:
                            # For matched locations, use the gid and displacement reason
                            VariableData.objects.filter(
                                variable=variable,
                                start_date=start_date,
                                gid_id=key_id,
                                text=text_value,
                            ).update(
                                end_date=record_data["end_date"],
                                period=record_data["period"],
                                adm_level=record_data["adm_level"],
                                value=record_data["value"],
                                raw_data=record_data["raw_data"],
                                original_location_text=record_data["original_location_text"],
                                unmatched_location=record_data["unmatched_location"],
                                updated_at=record_data["updated_at"],
                            )
                        update_count += 1
                        if update_count % 1000 == 0:
                            self.log_info(f"Updated {update_count} records")

            # Determine success - either we processed records OR there were no records to process (both are success cases)
            total_records_handled = len(records_to_create) + len(records_to_update)

            if total_records_handled > 0:
                self.log_info(f"Processing complete. Created: {len(records_to_create)}, Updated: {len(records_to_update)}, Skipped: {skipped_count}")
                return True
            elif len(results) == 0:
                self.log_info("Processing complete. No records to process after filtering (this is normal for incremental updates)")
                return True  # No records to process is success for incremental updates
            else:
                self.log_info(f"Processing complete. No records were successfully processed. Created: 0, Updated: 0, Skipped: {skipped_count}")
                return False  # Had records but couldn't process any - this is failure

        except Exception as e:
            self.log_error(f"Failed to process data for {variable.code}", error=e)
            return False

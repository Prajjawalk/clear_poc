"""FEWSNET (Famine Early Warning Systems Network) API data source implementation."""

import json
import os
import tempfile
import zipfile
from datetime import datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from django.db import transaction
from django.utils import timezone
from shapely import wkt

from location.models import Location

from ..base_source import Source
from ..models import Variable, VariableData


class FEWSNET(Source):
    """FEWSNET API source implementation.

    Retrieves food security data from FEWSNET's IPC package API.
    Downloads shapefiles and performs spatial overlay with ADM1 and ADM2 boundaries
    to calculate area-weighted food insecurity indicators.

    API Documentation: https://fdw.fews.net/

    Endpoint: https://fdw.fews.net/api/ipcpackage/country/{country_code}/{date}/
    Format: Shapefile ZIP package containing ML1 (food insecurity classification)

    Variables extracted:
        - fewsnet_food_insecurity: IPC food insecurity classification (1-5 scale)

    Notes:
        - FEWSNET shapefiles don't match standard ADM1/ADM2 boundaries
        - Uses spatial overlay to aggregate to both ADM1 and ADM2 levels
        - Area-weighted aggregation for accurate representation
        - Downloads shapefiles once and processes for both admin levels
    """

    def __init__(self, source_model):
        """Initialize FEWSNET source with metadata."""
        super().__init__(source_model)
        self.base_url = "https://fdw.fews.net/api/ipcpackage/country"
        self.country_code = "SD"  # Sudan

    def get_required_env_vars(self) -> list[str]:
        """FEWSNET doesn't require credentials."""
        return []

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw FEWSNET shapefile data from API.

        Args:
            variable: Variable instance to retrieve data for
            **kwargs: Optional start_date and end_date

        Returns:
            bool: True if data retrieval was successful
        """
        try:
            self.log_info(f"Starting FEWSNET data retrieval for {variable.code}")

            # Get date range
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")

            if not start_date or not end_date:
                # Default to last 1 month
                end_date = timezone.now().date()
                start_date = end_date

            # Convert to monthly periods
            start_period = pd.Period(start_date, freq="M")
            end_period = pd.Period(end_date, freq="M")
            period_range = pd.period_range(start=start_period, end=end_period, freq="M")

            self.log_info(f"Fetching data for {len(period_range)} months ({start_period} to {end_period})")

            # Create raw data directory
            raw_data_dir = self.get_raw_data_path(variable)
            os.makedirs(raw_data_dir, exist_ok=True)

            # Download shapefiles for each month
            success_count = 0
            for period in period_range:
                url = f"{self.base_url}/{self.country_code}/{period}-01/"
                output_file = os.path.join(raw_data_dir, f"{self.country_code}_{period}.zip")

                if self._download_shapefile(url, output_file, period):
                    success_count += 1

            if success_count == 0:
                self.log_warning(f"No data available for any period in range {start_period} to {end_period}")
            else:
                self.log_info(f"Successfully downloaded {success_count}/{len(period_range)} shapefiles")

            # Always return True - it's not an error if no data is available
            # The process() method will handle the case of no downloaded files
            return True

        except Exception as e:
            self.log_error(f"Failed to retrieve FEWSNET data: {e}")
            return False

    def _download_shapefile(self, url: str, output_file: str, period: pd.Period) -> bool:
        """Download a single FEWSNET shapefile using streaming.

        Args:
            url: API endpoint URL
            output_file: Path to save the ZIP file
            period: Period being downloaded

        Returns:
            bool: True if download was successful
        """
        try:
            self.log_info(f"Downloading {self.country_code}/{period}")

            response = requests.get(url, stream=True, timeout=60)
            if response.status_code != 200:
                self.log_warning(f"Failed to download {url} (status: {response.status_code})")
                return False

            # Save ZIP file using streaming
            total_size = 0
            with open(output_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            # Verify it's a valid ZIP
            try:
                with zipfile.ZipFile(output_file, "r") as zip_ref:
                    # Check if ML1.shp exists in the archive
                    files = zip_ref.namelist()
                    if not any("ML1.shp" in f for f in files):
                        self.log_warning(f"No ML1.shp found in {output_file}")
                        os.remove(output_file)
                        return False

                self.log_info(f" -> Saved {os.path.basename(output_file)} ({total_size} bytes)")
                return True

            except zipfile.BadZipFile:
                self.log_info(f" -> No data for {period}")
                if os.path.exists(output_file):
                    os.remove(output_file)
                return False

        except Exception as e:
            self.log_error(f"Error downloading {url}: {e}")
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process raw FEWSNET shapefiles into standardized format.

        Performs spatial overlay with ADM1 and ADM2 boundaries and calculates
        area-weighted food insecurity values.

        Args:
            variable: Variable instance to process data for
            **kwargs: Additional processing parameters

        Returns:
            bool: True if processing was successful
        """
        try:
            self.log_info(f"Starting FEWSNET data processing for {variable.code}")

            # Find the raw data directory - look for most recent directory matching pattern
            base_dir = f"raw_data/{self.source_model.name}"
            if not os.path.exists(base_dir):
                self.log_error(f"Raw data base directory not found: {base_dir}")
                return False

            # Find all directories matching the pattern
            pattern = f"{self.source_model.name}_{variable.code}_"
            matching_dirs = [
                d for d in os.listdir(base_dir)
                if os.path.isdir(os.path.join(base_dir, d)) and d.startswith(pattern)
            ]

            if not matching_dirs:
                self.log_error(f"No raw data directory found matching pattern: {pattern}")
                return False

            # Use the most recent directory (sorted by name, which includes timestamp)
            raw_data_dir = os.path.join(base_dir, sorted(matching_dirs)[-1])
            self.log_info(f"Using raw data directory: {raw_data_dir}")

            # Find all ZIP files
            zip_files = [f for f in os.listdir(raw_data_dir) if f.endswith(".zip")]
            if not zip_files:
                self.log_warning("No shapefile ZIP files found - no data available for the requested period")
                return True  # Not an error - just no data available

            self.log_info(f"Found {len(zip_files)} shapefiles to process")

            # Load ADM1 and ADM2 boundaries from database
            # Note: admin_level.code represents the hierarchical level (1=state, 2=locality, etc.)
            adm1_locations = Location.objects.filter(admin_level__code="1")
            adm2_locations = Location.objects.filter(admin_level__code="2")

            if not adm1_locations.exists():
                self.log_error("No ADM1 locations found in database (admin_level.code='1')")
                return False

            # Create GeoDataFrame for ADM1 locations (code='1')
            # Pass the code value for consistency in logs and raw_data
            adm1_gdf = self._create_adm_geodataframe(adm1_locations, admin_level_code="1")

            # Create GeoDataFrame for ADM2 locations (code='2') if any exist
            adm2_gdf = None
            if adm2_locations.exists():
                adm2_gdf = self._create_adm_geodataframe(adm2_locations, admin_level_code="2")
                self.log_info(f"Will process both ADM1 ({len(adm1_gdf)}) and ADM2 ({len(adm2_gdf)}) locations")
            else:
                self.log_info(f"Will process ADM1 ({len(adm1_gdf)}) locations only - no ADM2 boundaries found")

            # Process each shapefile
            all_data = []
            for zip_file in zip_files:
                zip_path = os.path.join(raw_data_dir, zip_file)
                period = self._extract_period_from_filename(zip_file)

                if period:
                    processed_data = self._process_shapefile(zip_path, period, adm1_gdf, adm2_gdf)
                    if processed_data:
                        all_data.extend(processed_data)

            if not all_data:
                self.log_warning("No data was successfully processed")
                return False

            # Save to database
            self._save_to_database(variable, all_data)

            self.log_info(f"Successfully processed {len(all_data)} records")
            return True

        except Exception as e:
            self.log_error(f"Failed to process FEWSNET data: {e}")
            return False

    def _create_adm_geodataframe(self, locations, admin_level_code: str) -> gpd.GeoDataFrame:
        """Create GeoDataFrame from Location objects at any admin level.

        Args:
            locations: QuerySet of Location objects
            admin_level_code: Admin level code as string ('1', '2', etc.)

        Returns:
            GeoDataFrame with administrative boundaries
        """
        data = []
        for loc in locations:
            if loc.boundary is not None:
                # Convert Django GEOS geometry to Shapely geometry
                # Use WKT to ensure proper conversion
                shapely_geom = wkt.loads(loc.boundary.wkt)

                data.append(
                    {
                        "location_id": loc.id,
                        "pcode": loc.geo_id,
                        "name": loc.name,
                        "admin_level_code": admin_level_code,
                        "geometry": shapely_geom,
                    }
                )

        if not data:
            self.log_error(f"No ADM{admin_level_code} locations with valid boundaries found")
            return gpd.GeoDataFrame()

        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326", geometry="geometry")
        self.log_info(f"Created GeoDataFrame with {len(gdf)} ADM{admin_level_code} boundaries")
        return gdf

    def _extract_period_from_filename(self, filename: str) -> pd.Period | None:
        """Extract period from filename (e.g., 'SD_2024-01.zip' -> Period('2024-01', 'M')).

        Args:
            filename: ZIP filename

        Returns:
            Period object or None if extraction fails
        """
        try:
            # Expected format: SD_2024-01.zip
            parts = filename.replace(".zip", "").split("_")
            if len(parts) >= 2:
                period_str = parts[1]  # e.g., '2024-01'
                return pd.Period(period_str, freq="M")
        except Exception as e:
            self.log_warning(f"Failed to extract period from {filename}: {e}")
        return None

    def _process_shapefile(self, zip_path: str, period: pd.Period, adm1_gdf: gpd.GeoDataFrame, adm2_gdf: gpd.GeoDataFrame | None = None) -> list:
        """Process a single FEWSNET shapefile with spatial overlay.

        Args:
            zip_path: Path to ZIP file containing shapefile
            period: Period for this data
            adm1_gdf: GeoDataFrame with ADM1 boundaries
            adm2_gdf: GeoDataFrame with ADM2 boundaries (optional)

        Returns:
            List of dictionaries with processed data
        """
        try:
            self.log_info(f"Processing {os.path.basename(zip_path)} for {period}")

            # Extract and read shapefile
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    with zipfile.ZipFile(zip_path, "r") as zip_ref:
                        zip_ref.extractall(tmpdir)
                except zipfile.BadZipFile:
                    self.log_warning(f"Invalid ZIP file: {zip_path}")
                    return []
                except Exception as e:
                    self.log_error(f"Failed to extract {zip_path}: {e}")
                    return []

                # Find ML1 shapefile
                shapefile_path = None
                for root, dirs, files in os.walk(tmpdir):
                    for file in files:
                        if "ML1.shp" in file:
                            shapefile_path = os.path.join(root, file)
                            break
                    if shapefile_path:
                        break

                if not shapefile_path:
                    self.log_warning(f"No ML1.shp found in {zip_path}")
                    return []

                # Read FEWSNET data with error handling
                try:
                    fews_gdf = gpd.read_file(shapefile_path)
                except Exception as e:
                    self.log_error(f"Failed to read shapefile {shapefile_path}: {e}")
                    return []

                if fews_gdf.empty:
                    self.log_warning(f"Empty shapefile: {shapefile_path}")
                    return []

                # Check if ML1 column exists
                if 'ML1' not in fews_gdf.columns:
                    self.log_warning(f"ML1 column not found in {shapefile_path}. Columns: {list(fews_gdf.columns)}")
                    return []

                self.log_info(f" -> Found {len(fews_gdf)} features")

                # Perform spatial overlay for ADM1
                all_data = []
                adm1_data = self._spatial_overlay(fews_gdf, adm1_gdf, period)
                if adm1_data:
                    all_data.extend(adm1_data)

                # Perform spatial overlay for ADM2 if available
                if adm2_gdf is not None and not adm2_gdf.empty:
                    adm2_data = self._spatial_overlay(fews_gdf, adm2_gdf, period)
                    if adm2_data:
                        all_data.extend(adm2_data)

                return all_data

        except Exception as e:
            self.log_error(f"Error processing {zip_path}: {e}")
            return []

    def _spatial_overlay(self, fews_gdf: gpd.GeoDataFrame, adm_gdf: gpd.GeoDataFrame, period: pd.Period) -> list:
        """Perform spatial overlay and calculate area-weighted values.

        Args:
            fews_gdf: GeoDataFrame with FEWSNET food insecurity data
            adm_gdf: GeoDataFrame with administrative boundaries (ADM1 or ADM2)
            period: Period for this data

        Returns:
            List of dictionaries with aggregated data at specified admin level
        """
        # Get admin level code from the first row (all rows have same level)
        admin_level_code = adm_gdf.iloc[0]['admin_level_code'] if not adm_gdf.empty else "1"
        try:
            # Ensure same CRS
            if fews_gdf.crs != adm_gdf.crs:
                try:
                    fews_gdf = fews_gdf.to_crs(adm_gdf.crs)
                except Exception as e:
                    self.log_error(f"Failed to reproject data: {e}")
                    return []

            # Simplify geometries for faster processing
            fews_gdf = fews_gdf.copy()
            try:
                fews_gdf.geometry = fews_gdf.geometry.simplify(0.005)
            except Exception as e:
                self.log_warning(f"Failed to simplify geometries: {e}")
                # Continue without simplification

            # Perform intersection with timeout protection
            try:
                self.log_info(f" -> Performing spatial overlay...")
                overlay_gdf = gpd.overlay(fews_gdf, adm_gdf, how="intersection", keep_geom_type=True)
            except Exception as e:
                self.log_error(f"Spatial overlay failed: {e}")
                return []

            if overlay_gdf.empty:
                self.log_warning(f"No spatial overlap found for {period}")
                return []

            # Extract food insecurity value (ML1 column)
            # Cap at 5 (IPC scale is 1-5)
            try:
                overlay_gdf["food_insecurity"] = np.minimum(overlay_gdf["ML1"], 5)
            except Exception as e:
                self.log_error(f"Failed to extract ML1 values: {e}")
                return []

            # Calculate area for weighting (use equal-area projection)
            try:
                self.log_info(f" -> Calculating areas...")
                overlay_gdf["area"] = overlay_gdf.to_crs("ESRI:102022").geometry.area  # Africa Albers Equal Area
            except Exception as e:
                self.log_error(f"Failed to calculate areas: {e}")
                return []

            # Calculate weighted values
            overlay_gdf["weighted_value"] = overlay_gdf["food_insecurity"] * overlay_gdf["area"]

            # Aggregate by location
            try:
                self.log_info(f" -> Aggregating to ADM{admin_level_code} level...")
                aggregated = (
                    overlay_gdf.groupby("location_id")
                    .agg({"area": "sum", "weighted_value": "sum", "pcode": "first", "name": "first", "admin_level_code": "first"})
                    .reset_index()
                )
            except Exception as e:
                self.log_error(f"Failed to aggregate data: {e}")
                return []

            # Calculate area-weighted average
            aggregated["value"] = aggregated["weighted_value"] / aggregated["area"]

            # Prepare output
            result = []
            for _, row in aggregated.iterrows():
                # Get Location object
                try:
                    location = Location.objects.get(id=row["location_id"])

                    # Convert period to dates
                    start_date = period.to_timestamp().date()
                    end_date = (period + 1).to_timestamp().date()

                    result.append(
                        {
                            "location": location,
                            "start_date": start_date,
                            "end_date": end_date,
                            "period": "month",
                            "value": round(row["value"], 2),
                            "text": f"Food insecurity (IPC {round(row['value'], 1)}) in {row['name']} ({period})",
                            "raw_data": {
                                "period": str(period),
                                "pcode": row["pcode"],
                                "location_name": row["name"],
                                "area_km2": round(row["area"] / 1e6, 2),  # Convert to km²
                                "admin_level_code": str(row["admin_level_code"]),
                            },
                        }
                    )
                except Location.DoesNotExist:
                    self.log_warning(f"Location {row['location_id']} not found")
                    continue

            self.log_info(f" -> Aggregated to {len(result)} ADM{admin_level_code} locations")
            return result

        except Exception as e:
            self.log_error(f"Error in spatial overlay: {e}")
            return []

    def _save_to_database(self, variable: Variable, data: list):
        """Save processed data to database.

        Args:
            variable: Variable instance
            data: List of dictionaries with processed data
        """
        with transaction.atomic():
            # Delete existing data for this variable (optional - depends on update strategy)
            # VariableData.objects.filter(variable=variable).delete()

            # Create new records
            for record in data:
                location = record["location"]
                VariableData.objects.update_or_create(
                    variable=variable,
                    gid=location,
                    start_date=record["start_date"],
                    end_date=record["end_date"],
                    defaults={
                        "adm_level": location.admin_level,
                        "period": record["period"],
                        "value": record["value"],
                        "text": record["text"],
                        "raw_data": record["raw_data"],
                        "created_at": timezone.now(),
                    },
                )

    # Logging helper methods
    def log_info(self, message: str):
        """Log info message."""
        self.logger.info(message)

    def log_warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)

    def log_error(self, message: str):
        """Log error message."""
        self.logger.error(message)

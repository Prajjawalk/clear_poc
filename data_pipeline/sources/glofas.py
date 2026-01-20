"""GloFAS (Global Flood Awareness System) data source implementation.

Retrieves and processes flood mapping data from the Copernicus Emergency Management Service
Global Flood Awareness System (GloFAS) Rapid Flood Mapping product.
"""

import os
import tempfile
import zipfile
from datetime import datetime

import geopandas as gpd
import pandas as pd
import requests
from django.db import transaction
from django.utils import timezone
from rasterstats import zonal_stats
from shapely import wkt

from location.models import Location

from ..base_source import Source
from ..models import Variable, VariableData


class GloFAS(Source):
    """GloFAS (Global Flood Awareness System) source implementation.

    Retrieves daily flood extent mapping from GloFAS Rapid Flood Mapping API.
    Downloads shapefiles, overlays with administrative boundaries (ADM2),
    and calculates affected population using GHSL population raster.

    API Documentation: https://european-flood.emergency.copernicus.eu/
    Endpoint: https://european-flood.emergency.copernicus.eu/api/fms/download/glofas/RapidFloodMapping/{date}/

    Variables extracted:
        - glofas_flood_population: Estimated population at high risk of being affected by floods (ADM2 level)

    Notes:
        - Downloads daily flood extent shapefiles from Rapid Flood Mapping product
        - Uses spatial overlay to split flood geometries by ADM2 boundaries
        - Calculates population affected using GHSL population raster via zonal statistics
        - Requires GHSL population raster at raw_data/GHSL - Population/GHS_POP_E2025.tif
    """

    def __init__(self, source_model):
        """Initialize GloFAS Rapid Flood Mapping source with metadata."""
        super().__init__(source_model)
        self.base_url = "https://european-flood.emergency.copernicus.eu/api/fms/download/glofas"
        self.product = "RapidFloodMapping"

    def get_required_env_vars(self) -> list[str]:
        """GloFAS Rapid Flood Mapping doesn't require credentials."""
        return []

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw GloFAS Rapid Flood Mapping shapefiles from API.

        Args:
            variable: Variable instance to retrieve data for
            **kwargs: Optional start_date and end_date

        Returns:
            bool: True if data retrieval was successful
        """
        try:
            self.log_info(f"Starting GloFAS Rapid Flood Mapping data retrieval for {variable.code}")

            # Get date range
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")

            if not start_date or not end_date:
                # Default to last 7 days
                end_date = timezone.now().date()
                start_date = end_date - pd.Timedelta(days=7)

            # Convert to daily periods
            start_period = pd.Period(start_date, freq="D")
            end_period = pd.Period(end_date, freq="D")
            period_range = pd.period_range(start=start_period, end=end_period, freq="D")

            self.log_info(f"Fetching data for {len(period_range)} days ({start_period} to {end_period})")

            # Create raw data directory
            raw_data_dir = self.get_raw_data_path(variable)
            os.makedirs(raw_data_dir, exist_ok=True)

            # Download shapefiles for each day
            success_count = 0
            for period in period_range:
                date_str = str(period)  # Format: 2025-08-20
                output_file = os.path.join(raw_data_dir, f"{date_str}.zip")

                if self._download_flood_shapefile(date_str, output_file):
                    success_count += 1

            if success_count == 0:
                self.log_warning(f"No data available for any date in range {start_period} to {end_period}")
            else:
                self.log_info(f"Successfully downloaded {success_count}/{len(period_range)} shapefiles")

            # Always return True - it's not an error if no data is available
            return True

        except Exception as e:
            self.log_error(f"Failed to retrieve GloFAS Rapid Flood Mapping data: {e}")
            return False

    def _download_flood_shapefile(self, date_str: str, output_file: str) -> bool:
        """Download a single GloFAS Rapid Flood Mapping shapefile.

        Args:
            date_str: Date string in YYYY-MM-DD format
            output_file: Path to save the ZIP file

        Returns:
            bool: True if download was successful
        """
        try:
            url = f"{self.base_url}/{self.product}/{date_str}/"
            self.log_info(f"Downloading flood data for {date_str}")

            response = requests.get(url, timeout=60)

            if response.status_code != 200:
                self.log_warning(f"Failed to download {url} (status: {response.status_code})")
                return False

            # Check for content-disposition header to get filename
            content_disposition = response.headers.get('content-disposition')
            if not content_disposition:
                self.log_warning(f"No filename in response for {date_str}")
                return False

            # Save ZIP file
            with open(output_file, "wb") as f:
                f.write(response.content)

            # Verify it's a valid ZIP and contains shapefiles
            try:
                with zipfile.ZipFile(output_file, "r") as zip_ref:
                    files = zip_ref.namelist()
                    shp_files = [f for f in files if f.endswith('.shp')]
                    if not shp_files:
                        self.log_warning(f"No shapefile found in {output_file}")
                        os.remove(output_file)
                        return False

                self.log_info(f" -> Saved {os.path.basename(output_file)} ({len(response.content)} bytes)")
                return True

            except zipfile.BadZipFile:
                self.log_warning(f"Invalid ZIP file for {date_str}")
                if os.path.exists(output_file):
                    os.remove(output_file)
                return False

        except Exception as e:
            self.log_error(f"Error downloading {url}: {e}")
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process raw GloFAS flood shapefiles into standardized format.

        Performs spatial overlay with ADM2 boundaries and calculates
        affected population using zonal statistics on GHSL population raster.

        Args:
            variable: Variable instance to process data for
            **kwargs: Additional processing parameters

        Returns:
            bool: True if processing was successful
        """
        try:
            self.log_info(f"Starting GloFAS Rapid Flood Mapping data processing for {variable.code}")

            # Find the raw data directory
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

            # Use the most recent directory
            raw_data_dir = os.path.join(base_dir, sorted(matching_dirs)[-1])
            self.log_info(f"Using raw data directory: {raw_data_dir}")

            # Find all ZIP files
            zip_files = [f for f in os.listdir(raw_data_dir) if f.endswith(".zip")]
            if not zip_files:
                self.log_warning("No shapefile ZIP files found - no data available for the requested period")
                return True  # Not an error - just no data available

            self.log_info(f"Found {len(zip_files)} shapefiles to process")

            # Load ADM2 boundaries from database
            adm2_locations = Location.objects.filter(admin_level__code="2")
            if not adm2_locations.exists():
                self.log_error("No ADM2 locations found in database (admin_level.code='2')")
                return False

            # Create GeoDataFrame for ADM2 locations
            adm2_gdf = self._create_adm_geodataframe(adm2_locations)
            self.log_info(f"Loaded {len(adm2_gdf)} ADM2 boundaries")

            # Load population raster path
            population_raster = self._get_population_raster_path()
            if not os.path.exists(population_raster):
                self.log_error(f"Population raster not found: {population_raster}")
                return False

            # Process each shapefile
            all_data = []
            for zip_file in zip_files:
                zip_path = os.path.join(raw_data_dir, zip_file)
                date_str = self._extract_date_from_filename(zip_file)

                if date_str:
                    processed_data = self._process_shapefile(
                        zip_path, date_str, adm2_gdf, population_raster
                    )
                    if processed_data:
                        all_data.extend(processed_data)

            if not all_data:
                self.log_warning("No data was successfully processed")
                return True  # Not an error - just no floods detected

            # Save to database
            self._save_to_database(variable, all_data)

            self.log_info(f"Successfully processed {len(all_data)} records")
            return True

        except Exception as e:
            self.log_error(f"Failed to process GloFAS Rapid Flood Mapping data: {e}")
            import traceback
            self.log_error(traceback.format_exc())
            return False

    def _create_adm_geodataframe(self, locations) -> gpd.GeoDataFrame:
        """Create GeoDataFrame from Location objects.

        Args:
            locations: QuerySet of Location objects

        Returns:
            GeoDataFrame with administrative boundaries
        """
        data = []
        for loc in locations:
            if loc.boundary is not None:
                # Convert Django GEOS geometry to Shapely geometry
                shapely_geom = wkt.loads(loc.boundary.wkt)

                data.append(
                    {
                        "location_id": loc.id,
                        "pcode": loc.geo_id,
                        "name": loc.name,
                        "geometry": shapely_geom,
                    }
                )

        if not data:
            self.log_error("No ADM2 locations with valid boundaries found")
            return gpd.GeoDataFrame()

        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326", geometry="geometry")
        self.log_info(f"Created GeoDataFrame with {len(gdf)} ADM2 boundaries")
        return gdf

    def _get_population_raster_path(self) -> str:
        """Get path to GHSL population raster.

        Returns:
            Path to population raster file
        """
        # Try multiple possible locations
        possible_paths = [
            "raw_data/GHSL - Population/GHS_POP_E2025.tif",
            "raw_data/GHSL/GHS_POP_E2025.tif",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        # Return first path as default (will be caught by existence check in process)
        return possible_paths[0]

    def _extract_date_from_filename(self, filename: str) -> str | None:
        """Extract date from filename (e.g., '2025-08-20.zip' -> '2025-08-20').

        Args:
            filename: ZIP filename

        Returns:
            Date string or None if extraction fails
        """
        try:
            date_str = filename.replace(".zip", "")
            # Validate date format
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except Exception as e:
            self.log_warning(f"Failed to extract date from {filename}: {e}")
            return None

    def _process_shapefile(
        self,
        zip_path: str,
        date_str: str,
        adm2_gdf: gpd.GeoDataFrame,
        population_raster: str
    ) -> list:
        """Process a single GloFAS flood shapefile.

        Args:
            zip_path: Path to ZIP file containing shapefile
            date_str: Date string for this data
            adm2_gdf: GeoDataFrame with ADM2 boundaries
            population_raster: Path to population raster

        Returns:
            List of dictionaries with processed data
        """
        try:
            self.log_info(f"Processing {os.path.basename(zip_path)} for {date_str}")

            # Extract and read shapefile
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    with zipfile.ZipFile(zip_path, "r") as zip_ref:
                        zip_ref.extractall(tmpdir)
                except zipfile.BadZipFile:
                    self.log_warning(f"Invalid ZIP file: {zip_path}")
                    return []

                # Find shapefile in extracted directory
                shp_files = [
                    os.path.join(tmpdir, f)
                    for f in os.listdir(tmpdir)
                    if f.endswith('.shp')
                ]

                if not shp_files:
                    self.log_warning(f"No shapefile found in {zip_path}")
                    return []

                shapefile_path = shp_files[0]

                # Read flood data
                try:
                    floods_gdf = gpd.read_file(shapefile_path)
                except Exception as e:
                    self.log_error(f"Failed to read shapefile {shapefile_path}: {e}")
                    return []

                if floods_gdf.empty:
                    self.log_info(f"No flood features found for {date_str}")
                    return []

                self.log_info(f" -> Found {len(floods_gdf)} flood features")

                # Ensure same CRS
                if floods_gdf.crs != adm2_gdf.crs:
                    floods_gdf = floods_gdf.to_crs(adm2_gdf.crs)

                # Perform spatial overlay to split flood geometries by ADM2 boundaries
                self.log_info(" -> Performing spatial overlay...")
                floods_with_admin = gpd.overlay(floods_gdf, adm2_gdf, how='intersection')

                if floods_with_admin.empty:
                    self.log_info(f"No floods within ADM2 boundaries for {date_str}")
                    return []

                self.log_info(f" -> Created {len(floods_with_admin)} flood segments by admin area")

                # Calculate population affected using zonal statistics
                self.log_info(" -> Calculating affected population...")
                pop_stats = zonal_stats(
                    floods_with_admin,
                    population_raster,
                    stats=['sum'],
                    nodata=0
                )

                # Add population to GeoDataFrame
                floods_with_admin['pop_affected'] = [
                    stat['sum'] if stat['sum'] is not None else 0
                    for stat in pop_stats
                ]

                # Save the floods with admin dataframe
                export_dir = os.path.dirname(zip_path)
                export_name = os.path.basename(zip_path).removesuffix(".zip")
                export_path = os.path.join(export_dir, f"{export_name}.geojson")
                floods_with_admin.to_file(export_path)

                # Prepare output data
                result = []
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

                # Group by location and sum population
                location_pop = floods_with_admin.groupby('location_id').agg({
                    'pop_affected': 'sum',
                    'pcode': 'first',
                    'name': 'first'
                }).reset_index()

                for _, row in location_pop.iterrows():
                    if row['pop_affected'] <= 0:
                        continue

                    result.append({
                        "location_id": row["location_id"],
                        "location_name": row["name"],
                        "date": date_obj,
                        "value": round(row["pop_affected"]),
                        "pcode": row["pcode"],
                    })

                self.log_info(f" -> Processed {len(result)} ADM2 regions with affected population")
                return result

        except Exception as e:
            self.log_error(f"Error processing {zip_path}: {e}")
            import traceback
            self.log_error(traceback.format_exc())
            return []

    def _save_to_database(self, variable: Variable, data: list):
        """Save processed data to database.

        Args:
            variable: Variable instance
            data: List of dictionaries with processed data
        """
        with transaction.atomic():
            for record in data:
                # Get Location object
                try:
                    location = Location.objects.get(id=record["location_id"])
                except Location.DoesNotExist:
                    self.log_warning(f"Location {record['location_id']} not found")
                    continue

                VariableData.objects.update_or_create(
                    variable=variable,
                    gid=location,
                    start_date=record["date"],
                    end_date=record["date"],
                    defaults={
                        "adm_level": location.admin_level,
                        "period": "day",
                        "value": record["value"],
                        "text": f"GloFAS - Population Affected: {record['value']:.0f} people affected in {record['location_name']} ({record['date']})",
                        "raw_data": {
                            "date": str(record["date"]),
                            "pcode": record["pcode"],
                            "location_name": record["location_name"],
                            "admin_level_code": "2",
                        },
                        "created_at": timezone.now(),
                    },
                )

    # Logging helper methods (inherited from base Source class, but explicitly defined for clarity)
    def log_info(self, message: str):
        """Log info message."""
        self.logger.info(message)

    def log_warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)

    def log_error(self, message: str):
        """Log error message."""
        self.logger.error(message)

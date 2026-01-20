"""ACLED CAST data source implementation."""

import csv
import os
from io import StringIO
from typing import Any

import pandas as pd
import requests
from django.db import transaction
from django.utils import timezone

from ..base_source import Source
from ..models import Variable, VariableData


class ACLEDCAST(Source):
    """ACLED CAST (Conflict Alert System Tool) source implementation.

    CAST provides forecasted conflict event data aggregated
    at the state-month level (ADM1).

    Authentication:
    - Uses OAuth token-based authentication
    - Access token obtained via username/password grant

    API Documentation:
    - Getting Started: https://acleddata.com/api-documentation/getting-started
    - CAST Endpoint: https://acleddata.com/api-documentation/cast-endpoint

    Endpoint: https://acleddata.com/api/cast/read

    Variables extracted:
        - acled_cast_battles_forecast: Forecasted battles/armed clashes
        - acled_cast_erv_forecast: Forecasted explosions/remote violence
        - acled_cast_vac_forecast: Forecasted violence against civilians
        - acled_cast_forecast: Total forecasted conflicts

    Notes:
        - CAST data is aggregated at state-month level (ADM1)
        - Provides forecast predictions
        - Location matching required to map state names to local admin boundaries
        - Different from main ACLED endpoint which provides event-level data
    """

    BASE_URL = "https://acleddata.com"
    CAST_ENDPOINT = f"{BASE_URL}/api/cast/read"
    OAUTH_TOKEN_ENDPOINT = f"{BASE_URL}/oauth/token"

    def __init__(self, source_model):
        """Initialize ACLED CAST source with metadata."""
        super().__init__(source_model)
        self.country = "Sudan"
        self.session = requests.Session()

    def get_required_env_vars(self) -> list[str]:
        """ACLED CAST requires email and password for OAuth."""
        return ["ACLED_USERNAME", "ACLED_API_KEY"]

    def test_authentication(self) -> dict[str, Any]:
        """Test ACLED CAST OAuth authentication."""
        base_result = super().test_authentication()
        if base_result["status"] != "success":
            return base_result

        try:
            # Test actual OAuth authentication process
            success = self._authenticate()
            return {
                "status": "success" if success else "failed",
                "token_valid": success,
                "oauth_endpoint": self.OAUTH_TOKEN_ENDPOINT,
                "cast_endpoint": self.CAST_ENDPOINT
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _get_credentials(self) -> tuple[str, str]:
        """Get ACLED CAST credentials from environment."""
        email = os.getenv("ACLED_USERNAME")
        password = os.getenv("ACLED_API_KEY")

        if not email or not password:
            raise ValueError("ACLED_USERNAME and ACLED_API_KEY must be set in environment")

        return email, password

    def _authenticate(self) -> bool:
        """Authenticate with ACLED API and store persistent OAuth token.

        Uses the same credentials as the ACLED source (ACLED_USERNAME and ACLED_API_KEY).
        Tokens are shared between ACLED and ACLEDCAST endpoints.

        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            # Check for stored valid token first
            stored_token = self.get_valid_access_token()
            if stored_token:
                # Test if stored token is still valid
                test_response = self.session.get(
                    f"{self.CAST_ENDPOINT}?limit=1",
                    headers={"Authorization": f"Bearer {stored_token}"}
                )
                if test_response.status_code == 200:
                    self.log_info("Using stored ACLED OAuth token")
                    return True
                else:
                    self.log_info(f"Stored token invalid, status: {test_response.status_code}")
                    self.clear_auth_token()

            # Get credentials and authenticate
            username, password = self._get_credentials()

            self.log_info("Authenticating with ACLED OAuth API")

            data = {
                "username": username,
                "password": password,
                "grant_type": "password",
                "client_id": "acled"
            }

            response = self.session.post(self.OAUTH_TOKEN_ENDPOINT, data=data, timeout=30)

            if response.status_code != 200:
                self.log_error(f"ACLED OAuth authentication failed with status {response.status_code}")
                self.log_error(f"Response: {response.text}")
                return False

            token_data = response.json()

            if "access_token" not in token_data:
                self.log_error("No access_token in OAuth response")
                self.log_error(f"Response data: {token_data}")
                return False

            # Store token persistently (default 3600 seconds = 1 hour if not specified)
            expires_in = token_data.get("expires_in", 3600)

            self.store_auth_token(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token", ""),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=expires_in,
                metadata={
                    "scope": token_data.get("scope", ""),
                    "username": username,
                }
            )

            self.log_info(f"ACLED OAuth authentication successful for user {username}")
            return True

        except Exception as e:
            self.log_error("ACLED OAuth authentication failed", error=e)
            return False

    def _get_access_token(self) -> str:
        """Get valid OAuth access token, authenticating if necessary.

        Returns:
            str: Valid access token

        Raises:
            Exception: If authentication fails
        """
        # Try to get stored valid token
        token = self.get_valid_access_token()
        if token:
            return token

        # Authenticate if no valid token
        if not self._authenticate():
            raise Exception("Failed to authenticate with ACLED API")

        # Get the newly stored token
        token = self.get_valid_access_token()
        if not token:
            raise Exception("Authentication succeeded but no token available")

        return token

    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw ACLED CAST data from API.

        Args:
            variable: Variable instance to retrieve data for
            **kwargs: Optional start_date and end_date

        Returns:
            bool: True if data retrieval was successful
        """
        try:
            self.log_info(f"Starting ACLED CAST data retrieval for {variable.code}")

            # Get date range
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")

            if not start_date or not end_date:
                # Default to current month
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

            # Get OAuth token (will use cached token if still valid)
            try:
                token = self._get_access_token()
            except Exception as e:
                self.log_error(f"Failed to obtain OAuth token: {e}")
                return False

            # Fetch data for each period
            success_count = 0
            for period in period_range:
                if self._fetch_period_data(token, period, raw_data_dir):
                    success_count += 1

            if success_count == 0:
                self.log_warning(f"No data available for any period in range {start_period} to {end_period}")
            else:
                self.log_info(f"Successfully downloaded {success_count}/{len(period_range)} periods")

            # Always return True - it's not an error if no data is available
            return True

        except Exception as e:
            self.log_error(f"Failed to retrieve ACLED CAST data: {e}")
            return False

    def _fetch_period_data(self, token: str, period: pd.Period, raw_data_dir: str) -> bool:
        """Fetch CAST data for a specific period.

        Args:
            token: OAuth access token
            period: Period to fetch
            raw_data_dir: Directory to save raw data

        Returns:
            bool: True if fetch was successful
        """
        try:
            # Month number to English name mapping
            month_names = {
                1: "January", 2: "February", 3: "March", 4: "April",
                5: "May", 6: "June", 7: "July", 8: "August",
                9: "September", 10: "October", 11: "November", 12: "December"
            }

            year = period.year
            month = month_names[period.month]

            self.log_info(f"Fetching {self.country}/{year}/{month}")

            # Build query parameters
            params = {
                "_format": "csv",
                "country": self.country,
                "year": year,
                "month": month
            }

            # Make API request
            headers = {
                "Authorization": f"Bearer {token}"
            }

            response = requests.get(self.CAST_ENDPOINT, params=params, headers=headers, timeout=60)

            if response.status_code != 200:
                self.log_warning(f"Failed to fetch data for {period} (status: {response.status_code})")
                self.log_warning(f"Response headers: {dict(response.headers)}")
                self.log_warning(f"Response body: {response.text[:500]}")
                return False

            # Parse CSV response
            # Handle UTF-8 BOM if present
            csv_text = response.text
            if not csv_text.strip():
                self.log_info(f" -> No data for {period}")
                return False

            # Remove BOM if present (appears as \ufeff at start of text)
            if csv_text.startswith('\ufeff'):
                csv_text = csv_text[1:]

            csv_reader = csv.DictReader(StringIO(csv_text))
            data = list(csv_reader)

            if not data:
                self.log_info(f" -> No data for {period}")
                return False

            # Save to JSON file
            output_file = os.path.join(raw_data_dir, f"{period}.json")
            import json
            with open(output_file, "w") as f:
                json.dump(data, f, indent=2)

            self.log_info(f" -> Saved {len(data)} records ({len(csv_text)} bytes)")
            return True

        except Exception as e:
            self.log_error(f"Error fetching data for {period}: {e}")
            return False

    def process(self, variable: Variable, **kwargs) -> bool:
        """Process raw ACLED CAST data into standardized format.

        Args:
            variable: Variable instance to process data for
            **kwargs: Additional processing parameters

        Returns:
            bool: True if processing was successful
        """
        try:
            self.log_info(f"Starting ACLED CAST data processing for {variable.code}")

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

            # Find all JSON files
            import json
            json_files = [f for f in os.listdir(raw_data_dir) if f.endswith(".json")]
            if not json_files:
                self.log_warning("No JSON files found - no data available for the requested period")
                return True  # Not an error - just no data available

            self.log_info(f"Found {len(json_files)} data files to process")

            # Process each file
            all_data = []
            for json_file in json_files:
                file_path = os.path.join(raw_data_dir, json_file)
                period = self._extract_period_from_filename(json_file)

                if period:
                    processed_data = self._process_file(file_path, period, variable)
                    if processed_data:
                        all_data.extend(processed_data)

            if not all_data:
                self.log_warning("No data was successfully processed")
                return True  # Not an error

            # Save to database
            self._save_to_database(variable, all_data)

            self.log_info(f"Successfully processed {len(all_data)} records")
            return True

        except Exception as e:
            self.log_error(f"Failed to process ACLED CAST data: {e}")
            return False

    def _extract_period_from_filename(self, filename: str) -> pd.Period | None:
        """Extract period from filename (e.g., '2024-01.json' -> Period('2024-01', 'M')).

        Args:
            filename: JSON filename

        Returns:
            Period object or None if extraction fails
        """
        try:
            period_str = filename.replace(".json", "")
            return pd.Period(period_str, freq="M")
        except Exception as e:
            self.log_warning(f"Failed to extract period from {filename}: {e}")
        return None

    def _process_file(self, file_path: str, period: pd.Period, variable: Variable) -> list:
        """Process a single ACLED CAST data file.

        Args:
            file_path: Path to JSON file
            period: Period for this data
            variable: Variable being processed

        Returns:
            List of dictionaries with processed data
        """
        try:
            import json
            with open(file_path, "r") as f:
                data = json.load(f)

            if not data:
                return []

            self.log_info(f"Processing {len(data)} records for {period}")

            result = []
            for record in data:
                # Extract admin1 name for location matching
                admin1_name = record.get("admin1", "")
                if not admin1_name:
                    self.log_warning(f"No admin1 field found in record: {record}")
                    continue

                # Match location using validate_location_match
                context_data = {
                    "original_location": admin1_name,
                    "country": record.get("country", self.country),
                    "expected_admin_level": 1,
                    "source": "ACLED_CAST",
                }
                location = self.validate_location_match(admin1_name, "ACLED_CAST", context_data)

                if not location:
                    self.log_warning(f"Could not match location: {admin1_name}")
                    continue

                # Extract value based on variable code
                value = self._extract_variable_value(record, variable.code)
                if value is None:
                    continue

                # Convert period to dates
                start_date = period.to_timestamp().date()
                end_date = (period + 1).to_timestamp().date()

                result.append({
                    "location": location,
                    "start_date": start_date,
                    "end_date": end_date,
                    "period": "month",
                    "value": value,
                    "text": f"{variable.name}: {value} for {admin1_name} ({period})",
                    "raw_data": record,
                })

            return result

        except Exception as e:
            self.log_error(f"Error processing {file_path}: {e}")
            return []

    def _extract_variable_value(self, record: dict, variable_code: str) -> float | None:
        """Extract value for specific variable from CAST record.

        Args:
            record: CAST data record
            variable_code: Variable code to extract

        Returns:
            Numeric value or None if not found/applicable
        """
        # Map variable codes to CAST CSV columns
        # battles_forecast: Forecasted number of battles (armed clashes)
        # erv_forecast: Forecasted number of explosions/remote violence events
        # vac_forecast: Forecasted number of violence against civilians events
        column_mapping = {
            "acled_cast_battles_forecast": "battles_forecast",
            "acled_cast_erv_forecast": "erv_forecast",
            "acled_cast_vac_forecast": "vac_forecast",
            "acled_cast_forecast": "total_forecast",
        }

        column_name = column_mapping.get(variable_code)
        if not column_name:
            self.log_warning(f"Unknown variable code: {variable_code}")
            return None

        try:
            value_str = record.get(column_name, "")
            if not value_str or value_str == "":
                return None
            return float(value_str)
        except (ValueError, TypeError):
            return None

    def _save_to_database(self, variable: Variable, data: list):
        """Save processed data to database.

        Args:
            variable: Variable instance
            data: List of dictionaries with processed data
        """
        with transaction.atomic():
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


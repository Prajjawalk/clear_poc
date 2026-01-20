"""Z-score based multi-level anomaly detection for time series data."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from django.utils import timezone

from alert_framework.base_detector import BaseDetector
from data_pipeline.models import VariableData


class ZScoreDetector(BaseDetector):
    """Multi-level Z-score based anomaly detection for humanitarian data."""

    def __init__(self, detector_config):
        """Initialize Z-score detector with configuration."""
        super().__init__(detector_config)
        self._load_config()

    def _load_config(self, **config):
        """Initialize the detector with proper configuration."""
        config_dict = self.config.configuration or {}
        config_dict.update(config)

        # Z-score thresholds for 5 alert levels
        self.zscore_threshold_1 = config_dict.get("zscore_threshold_1", 1.5)  # Low alert
        self.zscore_threshold_2 = config_dict.get("zscore_threshold_2", 2.0)  # Medium alert
        self.zscore_threshold_3 = config_dict.get("zscore_threshold_3", 2.5)  # High alert
        self.zscore_threshold_4 = config_dict.get("zscore_threshold_4", 3.0)  # Critical alert

        # Window and baseline settings
        self.window_size = config_dict.get("window_size", 30)
        self.min_baseline_periods = config_dict.get("min_baseline_periods", 7)
        self.freq = config_dict.get("freq", "1D")

        # Data handling
        self.min_std = config_dict.get("min_std", 0.1)
        self.variable_code = config_dict.get("variable_code", None)  # Will be determined dynamically
        self.admin_level = config_dict.get("admin_level", 2)
        self.aggregation_func = config_dict.get("aggregation_func", "mean")  # Missing parameter

        # Alert filtering
        self.min_alert_level = config_dict.get("min_alert_level", 1)

    def _load_data(self, start_date=None, end_date=None):
        """Load the data from source."""
        if start_date is None or end_date is None:
            raise ValueError("start_date and end_date are required for data loading")

        # Find available variables if not specified
        if self.variable_code is None:
            from data_pipeline.models import Variable

            # Get variable filters from configuration
            variable_filters = self.config.configuration.get("variable_filters", {})
            variable_codes = variable_filters.get("variable_codes", [])  # No default - let it find any variable
            source_names = variable_filters.get("source_names", [])
            data_types = variable_filters.get("data_types", ["quantitative", "numeric"])

            # First, try to find variables by specific codes
            if variable_codes:
                variables = Variable.objects.filter(code__in=variable_codes).order_by("source__name", "code")

                if variables.exists():
                    self.variable_code = variables.first().code
                    source_name = variables.first().source.name
                    self.logger.info(f"Using variable by code: {self.variable_code} from source: {source_name}")
                else:
                    self.logger.warning(f"No variables found for codes: {variable_codes}")

            # If no specific codes found, try by source names
            if self.variable_code is None and source_names:
                for source_name in source_names:
                    variables = Variable.objects.filter(source__name__icontains=source_name, type__in=data_types).order_by("source__name", "code")

                    if variables.exists():
                        self.variable_code = variables.first().code
                        actual_source_name = variables.first().source.name
                        self.logger.info(f"Using variable by source: {self.variable_code} from source: {actual_source_name}")
                        break

            # Final fallback - any quantitative/numeric variable
            if self.variable_code is None:
                variables = Variable.objects.filter(type__in=data_types).order_by("source__name", "code")

                if not variables.exists():
                    self.logger.error(f"No variables found matching types: {data_types}")
                    return VariableData.objects.none()

                self.variable_code = variables.first().code
                source_name = variables.first().source.name
                self.logger.info(f"Using fallback variable: {self.variable_code} from source: {source_name}")

        # Extended date range to include baseline calculation data
        extended_start = start_date - timedelta(days=self.window_size + 30)

        data = self.get_variable_data(variable_code=self.variable_code, start_date=extended_start, end_date=end_date, admin_level=self.admin_level)

        return data

    def detect(self, start_date: datetime, end_date: datetime, **kwargs) -> list[dict]:
        """
        Analyze data within time window and return Z-score based detections.

        Args:
            start_date: Analysis window start
            end_date: Analysis window end
            **kwargs: Additional parameters

        Returns:
            List of detection dictionaries with Z-score anomalies
        """
        detections = []

        try:
            self.log_detection(
                "Starting Z-score anomaly detection",
                variable_code=self.variable_code,
                thresholds=[self.zscore_threshold_1, self.zscore_threshold_2, self.zscore_threshold_3, self.zscore_threshold_4],
                window_size=self.window_size,
            )

            # Load data with extended range for baseline calculation
            raw_data = self._load_data(start_date, end_date)

            if not raw_data.exists():
                self.log_detection("No data found for Z-score analysis")
                return detections

            # Convert Django QuerySet to pandas DataFrame
            df = self._queryset_to_dataframe(raw_data)

            if df.empty:
                self.log_detection("No valid data after conversion to DataFrame")
                return detections

            # Process time series data with Z-score analysis
            results_df = self._process_timeseries_data(df)

            # Filter for analysis period and alerts
            # Convert datetime to pandas timestamp for comparison, removing timezone info
            # to match the timezone-naive data in the DataFrame
            start_ts = pd.Timestamp(start_date).tz_localize(None) if hasattr(start_date, "tzinfo") and start_date.tzinfo else pd.Timestamp(start_date)
            end_ts = pd.Timestamp(end_date).tz_localize(None) if hasattr(end_date, "tzinfo") and end_date.tzinfo else pd.Timestamp(end_date)

            analysis_alerts = results_df[
                (results_df["date"] >= start_ts) & (results_df["date"] <= end_ts) & (results_df["alert_level"] >= self.min_alert_level) & (results_df["sufficient_baseline"])
            ]

            # Convert alerts to detection format
            for _, alert in analysis_alerts.iterrows():
                detection = self._create_detection_from_alert(alert, start_date, end_date)
                if detection:
                    detections.append(detection)

            self.log_detection(
                "Z-score anomaly detection completed", detections_found=len(detections), total_processed=len(results_df), analysis_period_alerts=len(analysis_alerts)
            )

        except Exception as e:
            self.log_detection(f"Z-score detection failed: {str(e)}", level="error")

        return detections

    def _queryset_to_dataframe(self, queryset) -> pd.DataFrame:
        """Convert Django QuerySet to pandas DataFrame for analysis with proper aggregation."""
        records = []

        for record in queryset:
            if record.gid_id:  # Only include records with matched locations
                records.append(
                    {
                        "date": record.start_date or record.end_date,
                        "unit_id": record.gid_id,
                        "value": float(record.value),
                    }
                )

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])

        # Aggregate data by frequency and unit (preserving irregular spacing for meaningful baseline calculations)
        df = df.set_index("date")

        # Group by frequency and unit_id, then aggregate using the specified function
        agg_dict = {"value": self.aggregation_func}
        if "location_name" in df.columns:
            agg_dict["location_name"] = "first"  # Keep the first location name for each group

        df_aggregated = df.groupby([pd.Grouper(freq=self.freq), "unit_id"]).agg(agg_dict)

        # Reset index to get date and unit_id as columns
        df_aggregated = df_aggregated.reset_index()

        # Sort by unit and date (critical for rolling window calculations)
        df_aggregated = df_aggregated.sort_values(["unit_id", "date"]).reset_index(drop=True)

        # Ensure value column is numeric and handle NaN values consistently with standalone script
        df_aggregated["value"] = pd.to_numeric(df_aggregated["value"], errors="coerce").fillna(0)

        return df_aggregated

    def _process_timeseries_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process time series data with multi-level Z-score anomaly detection."""
        if df.empty:
            return pd.DataFrame()

        # Calculate z-scores and alert levels
        result_df = self._calculate_zscore_and_alerts(df)

        # Add summary metrics
        result_df = self._add_summary_metrics(result_df)

        return result_df

    def _calculate_zscore_and_alerts(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Z-scores and multi-level alerts using pandas vectorized operations."""
        # Debug: Ensure data is sorted by unit_id and date (matching standalone script behavior)
        df = df.sort_values(["unit_id", "date"]).copy()

        # Calculate baseline statistics using rolling windows (excluding current observation)
        df["baseline_mean"] = df.groupby("unit_id")["value"].transform(lambda x: x.shift(1).rolling(window=self.window_size, min_periods=1).mean())

        df["baseline_std"] = df.groupby("unit_id")["value"].transform(
            lambda x: x.shift(1).rolling(window=self.window_size, min_periods=1).std().fillna(self.min_std).clip(lower=self.min_std)
        )

        # Count baseline periods available
        df["baseline_periods"] = df.groupby("unit_id")["value"].transform(lambda x: x.shift(1).rolling(window=self.window_size, min_periods=1).count())

        # Fill NaN values for first observations
        df["baseline_mean"] = df["baseline_mean"].fillna(df["value"])
        df["baseline_periods"] = df["baseline_periods"].fillna(0)

        # Calculate z-score: standardized deviation from baseline
        df["zscore"] = (df["value"] - df["baseline_mean"]) / df["baseline_std"]
        df["zscore_abs"] = np.abs(df["zscore"])

        # Generate multi-level alerts based on z-score thresholds
        df = self._generate_multilevel_alerts(df)

        # Round numeric columns for cleaner output
        numeric_cols = ["baseline_mean", "baseline_std", "zscore", "zscore_abs"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].round(5)

        return df.fillna(0)

    def _generate_multilevel_alerts(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate multi-level alert flags based on z-score thresholds."""
        # Check if we have sufficient baseline for alerting
        sufficient_baseline = df["baseline_periods"] >= self.min_baseline_periods

        # Initialize alert level column
        df["alert_level"] = 0

        # Set alert levels based on z-score thresholds (only when sufficient baseline)
        df.loc[sufficient_baseline & (df["zscore_abs"] >= self.zscore_threshold_1), "alert_level"] = 1
        df.loc[sufficient_baseline & (df["zscore_abs"] >= self.zscore_threshold_2), "alert_level"] = 2
        df.loc[sufficient_baseline & (df["zscore_abs"] >= self.zscore_threshold_3), "alert_level"] = 3
        df.loc[sufficient_baseline & (df["zscore_abs"] >= self.zscore_threshold_4), "alert_level"] = 4

        # Add alert level names for readability
        alert_level_names = {0: "No Alert", 1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
        df["alert_level_name"] = df["alert_level"].map(alert_level_names)

        # Boolean flag for any alert
        df["has_alert"] = df["alert_level"] > 0
        df["sufficient_baseline"] = sufficient_baseline

        # Add threshold info for reference
        df["threshold_exceeded"] = np.nan
        df.loc[df["alert_level"] == 1, "threshold_exceeded"] = self.zscore_threshold_1
        df.loc[df["alert_level"] == 2, "threshold_exceeded"] = self.zscore_threshold_2
        df.loc[df["alert_level"] == 3, "threshold_exceeded"] = self.zscore_threshold_3
        df.loc[df["alert_level"] == 4, "threshold_exceeded"] = self.zscore_threshold_4

        return df

    def _add_summary_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add summary metrics to results DataFrame."""
        df = df.copy()

        # Alert direction (above or below baseline)
        df["alert_direction"] = np.where(df["zscore"] > 0, "above_baseline", "below_baseline")

        # Deviation magnitude (how many standard deviations from baseline)
        df["deviation_magnitude"] = df["zscore_abs"]

        # Percentage deviation from baseline
        df["percent_deviation"] = ((df["value"] - df["baseline_mean"]) / df["baseline_mean"].clip(lower=0.01)) * 100
        df["percent_deviation"] = df["percent_deviation"].round(2)

        return df

    def _create_detection_from_alert(self, alert_row, start_date: datetime, end_date: datetime) -> dict | None:
        """Create a detection dictionary from an alert row."""
        try:
            # Get location object with admin_level
            from location.models import Location

            try:
                location = Location.objects.select_related("admin_level").get(id=alert_row["unit_id"])
            except Location.DoesNotExist:
                self.log_detection(f"Location {alert_row['unit_id']} not found", level="warning")
                return None

            # Get displacement reason for this location and date to determine shock type
            displacement_reason = self._get_displacement_reason(location, alert_row["date"])
            shock_type_id = self._map_displacement_reason_to_shock_type(displacement_reason)

            # Calculate confidence score based on z-score magnitude and baseline periods
            zscore_abs = alert_row.get("zscore_abs", 0)
            baseline_periods = alert_row.get("baseline_periods", 0)

            # Base confidence from z-score (higher z-score = higher confidence)
            base_confidence = min(0.95, max(0.1, (zscore_abs - 1.0) / 4.0))

            # Adjust based on baseline quality (more periods = higher confidence)
            baseline_factor = min(1.0, baseline_periods / self.window_size)
            confidence_score = base_confidence * baseline_factor

            # Determine shock type based on alert direction and magnitude
            alert_level = alert_row.get("alert_level", 0)
            alert_direction = alert_row.get("alert_direction", "above_baseline")

            if alert_direction == "above_baseline":
                shock_type_name = f"Anomalous Increase (Level {alert_level})"
            else:
                shock_type_name = f"Anomalous Decrease (Level {alert_level})"

            detection_data = {
                "variable_code": self.variable_code,
                "zscore": float(alert_row.get("zscore", 0)),
                "zscore_abs": float(zscore_abs),
                "alert_level": int(alert_level),
                "alert_level_name": alert_row.get("alert_level_name", "Unknown"),
                "baseline_mean": float(alert_row.get("baseline_mean", 0)),
                "baseline_std": float(alert_row.get("baseline_std", 0)),
                "baseline_periods": int(baseline_periods),
                "current_value": float(alert_row.get("value", 0)),
                "percent_deviation": float(alert_row.get("percent_deviation", 0)),
                "threshold_exceeded": float(alert_row.get("threshold_exceeded", 0)),
                "thresholds": [self.zscore_threshold_1, self.zscore_threshold_2, self.zscore_threshold_3, self.zscore_threshold_4],
                "aggregation_func": self.aggregation_func,
                "alert_direction": alert_direction,
                "window_size": self.window_size,
                "min_baseline_periods": self.min_baseline_periods,
            }

            self.log_detection(
                f"Z-score anomaly detected in {location.name}",
                alert_level=alert_level,
                zscore=float(alert_row.get("zscore", 0)),
                value=float(alert_row.get("value", 0)),
                baseline_mean=float(alert_row.get("baseline_mean", 0)),
                confidence=confidence_score,
            )

            # Get admin level info safely
            admin_level_code = "Unknown"
            try:
                if hasattr(location, "admin_level") and location.admin_level:
                    admin_level_code = location.admin_level.code
            except Exception as e:
                self.log_detection(f"Failed to get admin_level for location {location.id}: {str(e)}", level="warning")

            return {
                "detection_timestamp": alert_row["date"],
                "locations": [{"id": alert_row["unit_id"], "name": location.name, "admin_level": admin_level_code}],
                "confidence_score": confidence_score,
                "shock_type_name": shock_type_name,
                "shock_type_id": shock_type_id,
                "displacement_reason": displacement_reason,
                "detection_data": detection_data,
            }

        except Exception as e:
            self.log_detection(f"Failed to create detection from alert: {str(e)}", level="error")
            return None

    def _get_displacement_reason(self, location, date) -> str:
        """Get displacement reason for a specific location and date."""
        try:
            # Use the combined displacement variable which stores reason in text field
            displacement_reason_data = (
                self.get_variable_data(variable_code="iom_dtm_displacement", start_date=date, end_date=date, admin_level=self.admin_level).filter(gid=location).first()
            )

            if displacement_reason_data and displacement_reason_data.text:
                reason = str(displacement_reason_data.text).strip()
                # Convert unspecified reasons to "Unknown"
                if reason.lower() in ["no reason for displacement reported", "other reason"]:
                    return "Unknown"
                return reason
            else:
                return "Unknown"
        except Exception as e:
            self.log_detection(f"Failed to get displacement reason: {str(e)}", level="warning")
            return "Unknown"

    def _map_displacement_reason_to_shock_type(self, displacement_reason: str) -> int:
        """Map displacement reason to appropriate shock type ID."""
        if not displacement_reason or displacement_reason.strip() == "":
            return 1  # Default to Conflict

        reason_lower = displacement_reason.lower().strip()

        # Handle specific IOM displacement reason values (single or multiple):
        # "Conflict", "No reason for displacement reported", "Natural disaster",
        # "Economic reasons", "Conflict; Natural disaster", "Other reason"

        # Priority-based mapping (highest priority wins for multiple reasons)
        if "conflict" in reason_lower:
            return 1  # Conflict (highest priority)
        elif "natural disaster" in reason_lower:
            return 2  # Natural disasters
        elif "economic" in reason_lower:
            return 4  # Food security (economic displacement often food-related)
        elif any(phrase in reason_lower for phrase in ["no reason for displacement reported", "other reason"]):
            return 1  # Unknown/unspecified reasons
        else:
            # Fallback for any other reasons
            return 1  # Default to Unknown

    def get_configuration_schema(self) -> dict:
        """Return JSON schema for configuration validation."""
        return {
            "type": "object",
            "properties": {
                "variable_code": {"type": "string", "default": "displacement_count", "description": "Variable code for the data to analyze"},
                "zscore_threshold_1": {"type": "number", "minimum": 0.5, "maximum": 5.0, "default": 1.5, "description": "Z-score threshold for Low alert (Level 1)"},
                "zscore_threshold_2": {"type": "number", "minimum": 1.0, "maximum": 5.0, "default": 2.0, "description": "Z-score threshold for Medium alert (Level 2)"},
                "zscore_threshold_3": {"type": "number", "minimum": 1.5, "maximum": 5.0, "default": 2.5, "description": "Z-score threshold for High alert (Level 3)"},
                "zscore_threshold_4": {"type": "number", "minimum": 2.0, "maximum": 10.0, "default": 3.0, "description": "Z-score threshold for Critical alert (Level 4)"},
                "window_size": {"type": "integer", "minimum": 5, "maximum": 365, "default": 30, "description": "Number of periods for sliding window baseline calculation"},
                "min_baseline_periods": {"type": "integer", "minimum": 3, "maximum": 100, "default": 7, "description": "Minimum periods required before alerting"},
                "freq": {"type": "string", "enum": ["1D", "1W", "1M", "3M"], "default": "1D", "description": "Data aggregation frequency"},
                "min_std": {"type": "number", "minimum": 0.01, "maximum": 1.0, "default": 0.1, "description": "Minimum standard deviation to prevent division by zero"},
                "admin_level": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 2,
                    "description": "Administrative level for analysis (0=country, 1=state, 2=locality, etc.)",
                },
                "min_alert_level": {"type": "integer", "minimum": 1, "maximum": 4, "default": 1, "description": "Minimum alert level to include in detections"},
                "aggregation_func": {
                    "type": "string",
                    "enum": ["mean", "sum", "max", "min", "std", "count"],
                    "default": "mean",
                    "description": "Aggregation function for resampling data by frequency",
                },
            },
            "required": ["variable_code"],
        }

    def _get_detector_specific_context(self, detection) -> dict:
        """Get detector-specific context for template rendering."""
        data = detection.detection_data
        return {
            "zscore": data.get("zscore", 0),
            "zscore_abs": data.get("zscore_abs", 0),
            "alert_level": data.get("alert_level", 0),
            "alert_level_name": data.get("alert_level_name", "Unknown"),
            "current_value": data.get("current_value", 0),
            "baseline_mean": data.get("baseline_mean", 0),
            "baseline_std": data.get("baseline_std", 0),
            "percent_deviation": data.get("percent_deviation", 0),
            "threshold_exceeded": data.get("threshold_exceeded", 0),
            "alert_direction": data.get("alert_direction", "unknown"),
            "baseline_periods": data.get("baseline_periods", 0),
            "window_size": data.get("window_size", self.window_size),
        }

    def _calculate_severity(self, detection) -> int:
        """Calculate severity level (1-5) based on alert level, matching standalone detector logic."""
        alert_level = detection.detection_data.get("alert_level", 0)

        # Direct mapping from alert level to severity (matching standalone detector)
        # Level 0: No alert -> Severity 1 (lowest)
        # Level 1: Low -> Severity 2
        # Level 2: Medium -> Severity 3
        # Level 3: High -> Severity 4
        # Level 4: Critical -> Severity 5 (highest)
        severity_map = {
            0: 1,  # No Alert
            1: 2,  # Low
            2: 3,  # Medium
            3: 4,  # High
            4: 5,  # Critical
        }

        return severity_map.get(alert_level, 1)

    def _get_data_source_reference(self, detection) -> str:
        """Get data source reference for alert attribution."""
        variable_code = detection.detection_data.get("variable_code", "unknown")
        return f"{self.config.name} (Z-score analysis of {variable_code})"

    def _calculate_validity_period(self, detection) -> datetime:
        """Calculate alert validity end time based on data frequency and alert level."""
        alert_level = detection.detection_data.get("alert_level", 1)

        # Higher alert levels have longer validity periods
        validity_days = {
            1: 3,  # Low alerts valid for 3 days
            2: 5,  # Medium alerts valid for 5 days
            3: 7,  # High alerts valid for 7 days
            4: 10,  # Critical alerts valid for 10 days
        }.get(alert_level, 7)

        return timezone.now() + timedelta(days=validity_days)

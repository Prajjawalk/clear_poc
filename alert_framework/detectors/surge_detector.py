"""Statistical surge detection for conflict and displacement data."""

from collections import defaultdict
from datetime import datetime, timedelta

from django.db import models

from alert_framework.base_detector import BaseDetector


class ConflictSurgeDetector(BaseDetector):
    """Detects unusual increases in conflict events using statistical analysis."""

    def detect(self, start_date: datetime, end_date: datetime, **kwargs) -> list[dict]:
        """Detect conflict surges in the specified time window.

        Args:
            start_date: Analysis window start
            end_date: Analysis window end
            **kwargs: Additional parameters

        Returns:
            List of detection dictionaries
        """
        detections = []

        try:
            # Get configuration parameters
            config = self.config.configuration
            threshold_multiplier = config.get("threshold_multiplier", 2.0)
            min_events = config.get("min_events", 5)
            variable_code = config.get("variable_code", "acled_events")
            _analysis_period_days = config.get("analysis_period_days", 7)  # Currently unused
            lookback_period_days = config.get("lookback_period_days", 30)

            self.log_detection("Starting conflict surge analysis", variable_code=variable_code, threshold_multiplier=threshold_multiplier, min_events=min_events)

            # Get conflict event data for analysis period
            analysis_data = self.get_variable_data(
                variable_code=variable_code,
                start_date=start_date,
                end_date=end_date,
                admin_level=config.get("admin_level", 2),  # Default to locality level
            )

            if not analysis_data.exists():
                self.log_detection("No conflict data found for analysis period")
                return detections

            # Group data by location
            location_data = self._group_data_by_location(analysis_data)

            # Analyze each location for surges
            for location_id, events in location_data.items():
                surge_detection = self._analyze_location_surge(
                    location_id=location_id,
                    events=events,
                    threshold_multiplier=threshold_multiplier,
                    min_events=min_events,
                    analysis_start=start_date,
                    analysis_end=end_date,
                    lookback_days=lookback_period_days,
                    variable_code=variable_code,
                )

                if surge_detection:
                    detections.append(surge_detection)

            self.log_detection("Conflict surge analysis completed", detections_found=len(detections), locations_analyzed=len(location_data))

        except Exception as e:
            self.log_detection(f"Conflict surge detection failed: {str(e)}", level="error")

        return detections

    def _group_data_by_location(self, data: models.QuerySet) -> dict[int, list]:
        """Group variable data by location ID.

        Args:
            data: QuerySet of VariableData records

        Returns:
            Dictionary mapping location_id to list of data records
        """
        location_groups = defaultdict(list)

        for record in data:
            if record.gid_id:  # Only include records with matched locations
                location_groups[record.gid_id].append(record)

        return dict(location_groups)

    def _analyze_location_surge(
        self, location_id: int, events: list, threshold_multiplier: float, min_events: int, analysis_start: datetime, analysis_end: datetime, lookback_days: int, variable_code: str
    ) -> dict | None:
        """Analyze a specific location for surge patterns.

        Args:
            location_id: Location ID to analyze
            events: List of VariableData records for this location
            threshold_multiplier: Multiplier for surge detection threshold
            min_events: Minimum events required to trigger detection
            analysis_start: Analysis period start
            analysis_end: Analysis period end
            lookback_days: Days to look back for historical baseline
            variable_code: Variable code being analyzed

        Returns:
            Detection dictionary if surge detected, None otherwise
        """
        try:
            # Calculate recent event count (analysis period)
            recent_count = sum(record.value or 0 for record in events)

            if recent_count < min_events:
                return None

            # Get historical baseline data
            historical_avg = self._calculate_historical_baseline(
                location_id=location_id,
                variable_code=variable_code,
                reference_date=analysis_start,
                lookback_days=lookback_days,
                analysis_period_days=(analysis_end - analysis_start).days,
            )

            if historical_avg is None or historical_avg == 0:
                # No historical data or zero baseline - can't determine surge
                return None

            # Calculate surge factor
            surge_factor = recent_count / historical_avg

            # Check if surge threshold is met
            if surge_factor >= threshold_multiplier:
                # Get location object
                from location.models import Location

                try:
                    location = Location.objects.get(id=location_id)
                except Location.DoesNotExist:
                    self.log_detection(f"Location {location_id} not found", level="warning")
                    return None

                # Calculate confidence score
                confidence_score = min(0.95, max(0.1, (surge_factor - 1.0) / 3.0))

                detection_data = {
                    "variable_code": variable_code,
                    "recent_count": recent_count,
                    "historical_average": historical_avg,
                    "surge_factor": surge_factor,
                    "threshold_multiplier": threshold_multiplier,
                    "analysis_period_days": (analysis_end - analysis_start).days,
                    "lookback_period_days": lookback_days,
                    "events_analyzed": len(events),
                }

                self.log_detection(
                    f"Conflict surge detected in {location.name}", surge_factor=surge_factor, recent_count=recent_count, historical_avg=historical_avg, confidence=confidence_score
                )

                return {
                    "detection_timestamp": analysis_end,
                    "locations": [location_id],
                    "confidence_score": confidence_score,
                    "shock_type_name": "Conflict",
                    "detection_data": detection_data,
                }

        except Exception as e:
            self.log_detection(f"Location surge analysis failed for location {location_id}: {str(e)}", level="error")

        return None

    def _calculate_historical_baseline(self, location_id: int, variable_code: str, reference_date: datetime, lookback_days: int, analysis_period_days: int) -> float | None:
        """Calculate historical baseline average for comparison.

        Args:
            location_id: Location ID
            variable_code: Variable code to analyze
            reference_date: Reference date for lookback calculation
            lookback_days: Days to look back for historical data
            analysis_period_days: Length of analysis periods

        Returns:
            Historical average or None if insufficient data
        """
        try:
            # Calculate historical period boundaries
            historical_end = reference_date - timedelta(days=1)
            historical_start = historical_end - timedelta(days=lookback_days)

            # Get historical data
            historical_data = self.get_variable_data(variable_code=variable_code, start_date=historical_start, end_date=historical_end, locations=[location_id])

            if not historical_data.exists():
                return None

            # Group historical data into analysis-period-sized windows
            total_value = 0
            _period_count = 0  # Currently unused but may be needed for future counting logic

            # Simple approach: sum all historical values and divide by number of equivalent periods
            for record in historical_data:
                total_value += record.value or 0

            # Calculate number of equivalent analysis periods in historical data
            equivalent_periods = max(1, lookback_days / analysis_period_days)

            return total_value / equivalent_periods

        except Exception as e:
            self.log_detection(f"Historical baseline calculation failed: {str(e)}", level="error")
            return None

    def get_configuration_schema(self) -> dict:
        """Return configuration schema for conflict surge detector."""
        return {
            "type": "object",
            "properties": {
                "variable_code": {"type": "string", "default": "acled_events", "description": "Variable code for conflict event data"},
                "threshold_multiplier": {"type": "number", "minimum": 1.0, "maximum": 10.0, "default": 2.0, "description": "Multiplier for surge detection threshold"},
                "min_events": {"type": "integer", "minimum": 1, "maximum": 100, "default": 5, "description": "Minimum events required to trigger detection"},
                "analysis_period_days": {"type": "integer", "minimum": 1, "maximum": 30, "default": 7, "description": "Length of analysis period in days"},
                "lookback_period_days": {"type": "integer", "minimum": 7, "maximum": 365, "default": 30, "description": "Historical lookback period for baseline calculation"},
                "admin_level": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 2,
                    "description": "Administrative level for analysis (0=country, 1=state, 2=locality, etc.)",
                },
            },
            "required": ["variable_code"],
        }

    def _get_detector_specific_context(self, detection) -> dict:
        """Get detector-specific context for template rendering."""
        data = detection.detection_data
        return {
            "surge_factor": data.get("surge_factor", 0),
            "recent_count": data.get("recent_count", 0),
            "historical_average": data.get("historical_average", 0),
            "events_analyzed": data.get("events_analyzed", 0),
            "analysis_period_days": data.get("analysis_period_days", 0),
        }

    def _calculate_severity(self, detection) -> int:
        """Calculate severity based on surge factor."""
        surge_factor = detection.detection_data.get("surge_factor", 1.0)

        if surge_factor >= 5.0:
            return 5  # Critical surge
        elif surge_factor >= 3.0:
            return 4  # High surge
        elif surge_factor >= 2.0:
            return 3  # Moderate surge
        elif surge_factor >= 1.5:
            return 2  # Low surge
        else:
            return 1  # Minimal surge


class DisplacementSurgeDetector(BaseDetector):
    """Detects unusual increases in displacement events."""

    def detect(self, start_date: datetime, end_date: datetime, **kwargs) -> list[dict]:
        """Detect displacement surges in the specified time window.

        This detector analyzes IDMC displacement data for unusual patterns.
        """
        detections = []

        try:
            config = self.config.configuration
            threshold_multiplier = config.get("threshold_multiplier", 1.5)
            min_displaced = config.get("min_displaced", 100)
            variable_codes = config.get("variable_codes", ["idmc_gidd_conflict_displacement", "idmc_idu_displacement"])

            self.log_detection("Starting displacement surge analysis", variable_codes=variable_codes, threshold_multiplier=threshold_multiplier)

            for variable_code in variable_codes:
                variable_detections = self._analyze_displacement_variable(
                    variable_code=variable_code, start_date=start_date, end_date=end_date, threshold_multiplier=threshold_multiplier, min_displaced=min_displaced
                )
                detections.extend(variable_detections)

            self.log_detection("Displacement surge analysis completed", detections_found=len(detections))

        except Exception as e:
            self.log_detection(f"Displacement surge detection failed: {str(e)}", level="error")

        return detections

    def _analyze_displacement_variable(self, variable_code: str, start_date: datetime, end_date: datetime, threshold_multiplier: float, min_displaced: int) -> list[dict]:
        """Analyze displacement variable for surge patterns."""
        detections = []

        try:
            # Get displacement data
            displacement_data = self.get_variable_data(
                variable_code=variable_code, start_date=start_date, end_date=end_date, admin_level=self.config.configuration.get("admin_level", 1)
            )

            if not displacement_data.exists():
                return detections

            # Group by location and analyze
            location_data = self._group_data_by_location(displacement_data)

            for location_id, records in location_data.items():
                total_displaced = sum(record.value or 0 for record in records)

                if total_displaced >= min_displaced:
                    # Simple detection based on absolute threshold for now
                    # In production, this would compare against historical baselines

                    from location.models import Location

                    try:
                        location = Location.objects.get(id=location_id)
                    except Location.DoesNotExist:
                        continue

                    # Calculate confidence based on displacement volume
                    confidence_score = min(0.9, max(0.3, total_displaced / (min_displaced * 5)))

                    detections.append(
                        {
                            "detection_timestamp": end_date,
                            "locations": [location_id],
                            "confidence_score": confidence_score,
                            "shock_type_name": "Displacement",
                            "detection_data": {
                                "variable_code": variable_code,
                                "total_displaced": total_displaced,
                                "records_analyzed": len(records),
                                "displacement_type": self._classify_displacement_type(variable_code),
                            },
                        }
                    )

                    self.log_detection(
                        f"Displacement surge detected in {location.name}", total_displaced=total_displaced, displacement_type=self._classify_displacement_type(variable_code)
                    )

        except Exception as e:
            self.log_detection(f"Displacement variable analysis failed for {variable_code}: {str(e)}", level="error")

        return detections

    def _group_data_by_location(self, data: models.QuerySet) -> dict[int, list]:
        """Group variable data by location ID."""
        location_groups = defaultdict(list)

        for record in data:
            if record.gid_id:  # Only include records with matched locations
                location_groups[record.gid_id].append(record)

        return dict(location_groups)

    def _classify_displacement_type(self, variable_code: str) -> str:
        """Classify displacement type based on variable code."""
        if "conflict" in variable_code.lower():
            return "Conflict-induced displacement"
        elif "disaster" in variable_code.lower():
            return "Disaster-induced displacement"
        elif "idu" in variable_code.lower():
            return "Internal displacement update"
        else:
            return "Displacement event"

    def get_configuration_schema(self) -> dict:
        """Return configuration schema for displacement surge detector."""
        return {
            "type": "object",
            "properties": {
                "variable_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["idmc_gidd_conflict_displacement", "idmc_idu_displacement"],
                    "description": "Variable codes for displacement data",
                },
                "threshold_multiplier": {"type": "number", "minimum": 1.0, "maximum": 5.0, "default": 1.5, "description": "Multiplier for surge detection threshold"},
                "min_displaced": {"type": "integer", "minimum": 10, "maximum": 10000, "default": 100, "description": "Minimum displaced persons to trigger detection"},
                "admin_level": {"type": "integer", "minimum": 0, "maximum": 5, "default": 1, "description": "Administrative level for analysis"},
            },
            "required": ["variable_codes"],
        }

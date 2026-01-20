"""Deduplication logic for preventing redundant alerts."""

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from alert_framework.models import Detection


logger = logging.getLogger(__name__)


class DuplicationChecker:
    """Handles detection deduplication to prevent redundant alerts."""

    def __init__(self):
        """Initialize the deduplication checker."""
        self.logger = logger

    def is_duplicate(self, detection: "Detection") -> bool:
        """Check if detection is duplicate of existing detection.

        Args:
            detection: Detection instance to check

        Returns:
            bool: True if detection is duplicate, False otherwise
        """
        try:
            # Check if deduplication is disabled for this detector
            detector_config = detection.detector.configuration or {}
            if detector_config.get("disable_deduplication", False):
                self.logger.info(f"Deduplication disabled for detector {detection.detector.name}, allowing detection {detection.id}")
                return False

            # For POC phase, implement simple placeholder logic
            # In production, this would include sophisticated deduplication

            # Check for exact duplicate based on detector, timestamp, and locations
            existing_detection = self._find_exact_duplicate(detection)
            if existing_detection:
                self.logger.info(f"Exact duplicate found for detection {detection.id}", extra={"original_id": existing_detection.id})
                detection.mark_duplicate(existing_detection)
                return True

            # Check for temporal proximity duplicates
            temporal_duplicate = self._find_temporal_duplicate(detection)
            if temporal_duplicate:
                self.logger.info(f"Temporal duplicate found for detection {detection.id}", extra={"original_id": temporal_duplicate.id})
                detection.mark_duplicate(temporal_duplicate)
                return True

            # Check for geographic proximity duplicates
            geographic_duplicate = self._find_geographic_duplicate(detection)
            if geographic_duplicate:
                self.logger.info(f"Geographic duplicate found for detection {detection.id}", extra={"original_id": geographic_duplicate.id})
                detection.mark_duplicate(geographic_duplicate)
                return True

            return False

        except Exception as e:
            self.logger.error(f"Deduplication check failed for detection {detection.id}: {str(e)}")
            # In case of error, err on the side of not marking as duplicate
            return False

    def _find_exact_duplicate(self, detection: "Detection") -> Optional["Detection"]:
        """Find exact duplicate based on detector, timestamp, and locations."""
        try:
            from alert_framework.models import Detection

            # Get detection locations
            detection_locations = set(detection.locations.values_list("id", flat=True))

            if not detection_locations:
                return None

            # Look for detections from same detector with same timestamp
            candidates = (
                Detection.objects.filter(
                    detector=detection.detector,
                    detection_timestamp=detection.detection_timestamp,
                    status="pending",  # Only consider pending detections
                    duplicate_of__isnull=True,  # Exclude already marked duplicates
                )
                .exclude(
                    id=detection.id  # Exclude the detection being checked
                )
                .prefetch_related("locations")
            )

            for candidate in candidates:
                candidate_locations = set(candidate.locations.values_list("id", flat=True))

                # Check if locations match exactly
                if detection_locations == candidate_locations:
                    return candidate

            return None

        except Exception as e:
            self.logger.error(f"Exact duplicate check failed: {str(e)}")
            return None

    def _find_temporal_duplicate(self, detection: "Detection") -> Optional["Detection"]:
        """Find duplicate based on temporal proximity."""
        try:
            from alert_framework.models import Detection

            # Configuration for temporal proximity (can be made configurable later)
            proximity_hours = 6  # Consider detections within 6 hours as potential duplicates

            # Calculate time window
            start_time = detection.detection_timestamp - timedelta(hours=proximity_hours)
            end_time = detection.detection_timestamp + timedelta(hours=proximity_hours)

            # Get detection locations
            detection_locations = set(detection.locations.values_list("id", flat=True))

            if not detection_locations:
                return None

            # Look for similar detections within time window
            candidates = (
                Detection.objects.filter(
                    detector=detection.detector,
                    detection_timestamp__gte=start_time,
                    detection_timestamp__lte=end_time,
                    shock_type=detection.shock_type,
                    status="pending",
                    duplicate_of__isnull=True,
                )
                .exclude(id=detection.id)
                .prefetch_related("locations")
            )

            for candidate in candidates:
                candidate_locations = set(candidate.locations.values_list("id", flat=True))

                # Check if there's significant location overlap (50% or more)
                overlap = detection_locations.intersection(candidate_locations)
                if overlap and len(overlap) / len(detection_locations.union(candidate_locations)) >= 0.5:
                    return candidate

            return None

        except Exception as e:
            self.logger.error(f"Temporal duplicate check failed: {str(e)}")
            return None

    def _find_geographic_duplicate(self, detection: "Detection") -> Optional["Detection"]:
        """Find duplicate based on geographic proximity."""
        try:
            from alert_framework.models import Detection

            # Get detection locations
            detection_locations = list(detection.locations.all())

            if not detection_locations:
                return None

            # For POC, implement simple parent-child location relationship checking
            # In production, this could include spatial distance calculations

            # Look for detections in parent/child locations within recent timeframe
            recent_time = detection.detection_timestamp - timedelta(days=1)

            candidates = (
                Detection.objects.filter(
                    detector=detection.detector, shock_type=detection.shock_type, detection_timestamp__gte=recent_time, status="pending", duplicate_of__isnull=True
                )
                .exclude(id=detection.id)
                .prefetch_related("locations")
            )

            for candidate in candidates:
                candidate_locations = list(candidate.locations.all())

                # Check if any detection location is parent/child of candidate locations
                if self._has_hierarchical_relationship(detection_locations, candidate_locations):
                    return candidate

            return None

        except Exception as e:
            self.logger.error(f"Geographic duplicate check failed: {str(e)}")
            return None

    def _has_hierarchical_relationship(self, locations1: list, locations2: list) -> bool:
        """Check if two location sets have parent-child relationships."""
        try:
            # Simple implementation: check if any location in set1 is ancestor/descendant of set2
            for loc1 in locations1:
                for loc2 in locations2:
                    # Check if loc1 is ancestor of loc2 or vice versa
                    if self._is_ancestor_descendant(loc1, loc2):
                        return True

            return False

        except Exception as e:
            self.logger.error(f"Hierarchical relationship check failed: {str(e)}")
            return False

    def _is_ancestor_descendant(self, loc1, loc2) -> bool:
        """Check if two locations have ancestor-descendant relationship."""
        try:
            # Get ancestors for both locations (assuming Location model has get_ancestors method)
            loc1_ancestors = set(loc1.get_ancestors().values_list("id", flat=True))
            loc2_ancestors = set(loc2.get_ancestors().values_list("id", flat=True))

            # Check if loc1 is ancestor of loc2
            if loc1.id in loc2_ancestors:
                return True

            # Check if loc2 is ancestor of loc1
            if loc2.id in loc1_ancestors:
                return True

            return False

        except (AttributeError, Exception) as e:
            # If get_ancestors method doesn't exist or fails, use simple admin level comparison
            try:
                return loc1.admin_level != loc2.admin_level
            except Exception:
                self.logger.error(f"Ancestor-descendant check failed: {str(e)}")
                return False


# Singleton instance for easy access
duplication_checker = DuplicationChecker()

"""Generalized scoring detector based on raw data field values and text analysis."""

import re
from datetime import datetime
from typing import Any

from django.utils import timezone

from alert_framework.base_detector import BaseDetector
from data_pipeline.models import VariableData
from location.models import Location


class ScoringDetector(BaseDetector):
    """Generic detector that scores alerts based on configurable raw data field rules."""

    def __init__(self, detector_config):
        """Initialize scoring detector with configuration."""
        super().__init__(detector_config)
        self._load_config()

    def _load_config(self, **config):
        """Initialize the detector with configuration."""
        config_dict = self.config.configuration or {}
        config_dict.update(config)

        # Data source configuration
        self.variable_code = config_dict.get("variable_code", "alerts")
        self.source_name = config_dict.get("source_name", "")

        # Field-based scoring rules
        self.field_scores = config_dict.get("field_scores", {})

        # Text-based keyword scoring
        self.keyword_scores = config_dict.get("keyword_scores", {})
        self.keyword_max_mode = config_dict.get("keyword_max_mode", False)
        self.text_fields = config_dict.get("text_fields", ["headline", "text"])

        # Location-based multipliers
        self.location_multipliers = config_dict.get("location_multipliers", {})
        self.location_fields = config_dict.get("location_fields", ["estimatedEventLocation[0]", "location_name"])

        # Scoring thresholds
        self.thresholds = config_dict.get("thresholds", {"critical": 25, "high": 15, "medium": 8, "low": 4})

        # Detection settings
        self.min_detection_score = config_dict.get("min_detection_score", 8)
        self.base_score = config_dict.get("base_score", 1.0)

        # Temporal clustering settings
        self.enable_clustering = config_dict.get("enable_clustering", False)
        self.cluster_window_hours = config_dict.get("cluster_window_hours", 6)
        self.cluster_min_alerts = config_dict.get("cluster_min_alerts", 2)

        # Shock type mapping
        self.shock_type_mapping = config_dict.get("shock_type_mapping", {})

    def _load_data(self, start_date=None, end_date=None):
        """Load alert data from the database."""
        if start_date is None or end_date is None:
            raise ValueError("start_date and end_date are required for data loading")

        # Build query filters
        filters = {"start_date__gte": start_date.date(), "start_date__lte": end_date.date()}

        # Add variable code filter if specified
        if self.variable_code:
            filters["variable__code"] = self.variable_code

        # Add source name filter if specified
        if self.source_name:
            filters["variable__source__name__icontains"] = self.source_name

        data = VariableData.objects.filter(**filters).select_related("variable", "variable__source", "gid", "adm_level").order_by("start_date", "created_at")

        if not data.exists():
            self.logger.warning(f"No data found for filters: {filters}")

        return data

    def detect(self, start_date: datetime, end_date: datetime) -> list[dict]:
        """Analyze alerts using configurable scoring and return detections."""
        detections = []

        # Load the data
        data = self._load_data(start_date, end_date)

        if not data.exists():
            self.logger.info("No alerts found for the specified period")
            return detections

        # Convert to list for processing
        alerts = list(data)

        # Score each alert
        scored_alerts = []
        for alert_record in alerts:
            try:
                score_data = self._score_alert(alert_record)
                if score_data["score"] >= self.min_detection_score:
                    scored_alerts.append({"alert_record": alert_record, "score": score_data["score"], "level": score_data["level"], "components": score_data["components"]})
            except Exception as e:
                self.logger.error(f"Error scoring alert {alert_record.id}: {str(e)}")
                continue

        # Generate detections from high-scoring alerts
        for alert_data in scored_alerts:
            detection = self._create_detection(alert_data)
            if detection:
                detections.append(detection)

        # Generate cluster detections if enabled
        if self.enable_clustering:
            cluster_detections = self._detect_alert_clusters(scored_alerts)
            detections.extend(cluster_detections)

        self.logger.info(f"Generated {len(detections)} detections from {len(scored_alerts)} qualifying alerts")
        return detections

    def _score_alert(self, alert_record: VariableData) -> dict[str, Any]:
        """Score a single alert based on configured rules."""
        components = {"base_score": self.base_score, "field_scores": {}, "keyword_score": 0, "location_multiplier": 1.0}

        raw_data = alert_record.raw_data or {}

        # 1. Field-based scoring
        field_score = 0
        for field_path, score_rules in self.field_scores.items():
            field_value = self._get_field_value(raw_data, field_path, alert_record)
            field_contribution = self._score_field_value(field_value, score_rules)
            if field_contribution > 0:
                components["field_scores"][field_path] = field_contribution
                field_score += field_contribution

        # 2. Text-based keyword scoring
        text_content = self._extract_text_content(raw_data, alert_record)
        keyword_score = self._score_keywords(text_content)
        components["keyword_score"] = keyword_score

        # 3. Location-based multiplier
        location_name = self._extract_location_name(raw_data, alert_record)
        location_multiplier = self._get_location_multiplier(location_name)
        components["location_multiplier"] = location_multiplier

        # Calculate final score
        final_score = (components["base_score"] + field_score + keyword_score) * location_multiplier

        # Determine alert level
        level = self._get_alert_level(final_score)

        self.logger.debug(f"Alert {alert_record.id}: score={final_score:.2f}, level={level}")

        return {
            "score": final_score,
            "level": level,
            "components": components,
            "debug_info": {
                "text_content": text_content[:100] if text_content else "",
                "location_name": location_name,
                "raw_data_sample": {k: v for k, v in list(raw_data.items())[:3]},  # First 3 fields for debug
            },
        }

    def _get_field_value(self, raw_data: dict, field_path: str, alert_record: VariableData) -> Any:
        """Extract field value using dot notation and array indexing."""
        try:
            # Handle special fallback fields
            if field_path == "text_fallback":
                return alert_record.text or ""
            elif field_path == "location_fallback":
                return alert_record.original_location_text or ""

            # Handle special case for array fields that need to be treated as a whole
            # e.g., "alertTopics" should return the entire array for contains matching
            if field_path in raw_data and isinstance(raw_data[field_path], list):
                return raw_data[field_path]

            # Parse field path (e.g., "alertType.name" or "estimatedEventLocation[0]")
            current_value = raw_data

            # Split by dots and handle array indexing
            parts = field_path.split(".")
            for part in parts:
                if "[" in part and "]" in part:
                    # Handle array indexing like "estimatedEventLocation[0]"
                    field_name = part.split("[")[0]
                    index_str = part.split("[")[1].split("]")[0]

                    if field_name in current_value:
                        current_value = current_value[field_name]
                        if isinstance(current_value, list):
                            try:
                                index = int(index_str)
                                current_value = current_value[index] if index < len(current_value) else None
                            except (ValueError, IndexError):
                                return None
                        else:
                            return None
                    else:
                        return None
                else:
                    # Regular field access
                    if isinstance(current_value, dict) and part in current_value:
                        current_value = current_value[part]
                    else:
                        return None

            return current_value

        except Exception as e:
            self.logger.debug(f"Error extracting field {field_path}: {str(e)}")
            return None

    def _score_field_value(self, field_value: Any, score_rules: dict) -> float:
        """Score a field value based on configured rules."""
        if field_value is None:
            return 0.0

        # Check if this field should use max instead of sum for multiple matches
        use_max_mode = score_rules.get("_mode") == "max"
        scores = []

        # Handle different rule types
        for rule_type, rule_config in score_rules.items():
            if rule_type.startswith("_"):  # Skip metadata fields like "_mode"
                continue

            if rule_type == "exact_match":
                # Exact value matching: {"value1": score1, "value2": score2}
                if str(field_value) in rule_config:
                    scores.append(rule_config[str(field_value)])

            elif rule_type == "contains":
                # Text contains matching: {"substring1": score1, "substring2": score2}
                # Handle both arrays and strings
                if isinstance(field_value, list):
                    # For arrays like alertTopics, check each item
                    for item in field_value:
                        if isinstance(item, dict) and "name" in item:
                            # For objects with name field
                            item_str = item["name"].lower()
                        else:
                            # For simple strings in array
                            item_str = str(item).lower()

                        for substring, points in rule_config.items():
                            if substring.lower() in item_str:
                                scores.append(points)
                else:
                    # For simple strings
                    field_str = str(field_value).lower()
                    for substring, points in rule_config.items():
                        if substring.lower() in field_str:
                            scores.append(points)

            elif rule_type == "regex":
                # Regex pattern matching: {"pattern1": score1, "pattern2": score2}
                field_str = str(field_value)
                for pattern, points in rule_config.items():
                    if re.search(pattern, field_str, re.IGNORECASE):
                        scores.append(points)

            elif rule_type == "numeric":
                # Numeric threshold scoring: {">=": {"threshold": score}, "<": {"threshold": score}}
                try:
                    numeric_value = float(field_value)
                    for operator, config in rule_config.items():
                        threshold = config.get("threshold", 0)
                        points = config.get("score", 0)

                        if operator == ">=" and numeric_value >= threshold:
                            scores.append(points)
                        elif operator == ">" and numeric_value > threshold:
                            scores.append(points)
                        elif operator == "<=" and numeric_value <= threshold:
                            scores.append(points)
                        elif operator == "<" and numeric_value < threshold:
                            scores.append(points)
                        elif operator == "==" and numeric_value == threshold:
                            scores.append(points)
                except (ValueError, TypeError):
                    pass

        # Return max or sum based on mode
        if not scores:
            return 0.0
        elif use_max_mode:
            return max(scores)
        else:
            return sum(scores)

    def _extract_text_content(self, raw_data: dict, alert_record: VariableData) -> str:
        """Extract all text content for keyword analysis."""
        text_parts = []

        # Extract from configured text fields
        for field_path in self.text_fields:
            text_value = self._get_field_value(raw_data, field_path, alert_record)
            if text_value and isinstance(text_value, str):
                text_parts.append(text_value)

        # Fallback to record text field
        if not text_parts and alert_record.text:
            text_parts.append(alert_record.text)

        return " ".join(text_parts)

    def _score_keywords(self, text: str) -> float:
        """Score keywords in text content."""
        if not text or not self.keyword_scores:
            return 0.0

        text_lower = text.lower()
        scores = []
        matched_keywords = []

        for keyword, points in self.keyword_scores.items():
            if keyword.lower() in text_lower:
                scores.append(points)
                matched_keywords.append(f"{keyword}({points})")

        if not scores:
            return 0.0

        return max(scores) if self.keyword_max_mode else sum(scores)

    def _extract_location_name(self, raw_data: dict, alert_record: VariableData) -> str:
        """Extract location name from configured fields."""
        # Try configured location fields
        for field_path in self.location_fields:
            location_value = self._get_field_value(raw_data, field_path, alert_record)
            if location_value and isinstance(location_value, str):
                return location_value

        # Fallback to database location
        if alert_record.gid:
            return alert_record.gid.name

        return ""

    def _get_location_multiplier(self, location_name: str) -> float:
        """Get location-based score multiplier."""
        if not location_name or not self.location_multipliers:
            return 1.0

        # Check for location matches
        for location_key, multiplier in self.location_multipliers.items():
            if location_key.lower() in location_name.lower():
                return multiplier

        return 1.0

    def _get_alert_level(self, score: float) -> str:
        """Determine alert level from score."""
        if score >= self.thresholds.get("critical", 25):
            return "critical"
        elif score >= self.thresholds.get("high", 15):
            return "high"
        elif score >= self.thresholds.get("medium", 8):
            return "medium"
        elif score >= self.thresholds.get("low", 4):
            return "low"
        else:
            return "none"

    def _create_detection(self, alert_data: dict) -> dict | None:
        """Create detection dictionary from scored alert."""
        alert_record = alert_data["alert_record"]

        try:
            # Determine shock type
            shock_type_name = self._determine_shock_type(alert_record, alert_data)

            # Extract title from headline or use alert level as fallback
            raw_data = alert_record.raw_data or {}
            headline = raw_data.get("headline", "")
            title = headline[:200] if headline else f"{alert_data['level'].title()} Priority Alert - {alert_record.start_date.strftime('%Y-%m-%d')}"

            detection = {
                "title": title,
                "detection_timestamp": timezone.make_aware(datetime.combine(alert_record.start_date, datetime.min.time())),
                "locations": [alert_record.gid] if alert_record.gid else [],
                "confidence_score": min(alert_data["score"] / 30.0, 1.0),  # Normalize to 0-1
                "shock_type_name": shock_type_name,
                "detection_data": {
                    "alert_id": alert_record.id,
                    "score": alert_data["score"],
                    "alert_level": alert_data["level"],
                    "score_components": alert_data["components"],
                    "raw_data_fields": self._extract_relevant_fields(alert_record.raw_data or {}),
                    "source": f"{self.__class__.__name__}",
                },
            }

            return detection

        except Exception as e:
            self.logger.error(f"Error creating detection from alert {alert_record.id}: {str(e)}")
            return None

    def _determine_shock_type(self, alert_record: VariableData, alert_data: dict) -> str:
        """Determine shock type based on configuration and alert content."""
        raw_data = alert_record.raw_data or {}
        level = alert_data["level"]

        # Use configured shock type mapping
        for mapping_rule, shock_type in self.shock_type_mapping.items():
            if self._evaluate_shock_type_rule(mapping_rule, raw_data, alert_record, level):
                return shock_type

        # Default fallback - use "Conflict" as the most common type for Dataminr alerts
        # (Conflict, Food security, Health emergencies, Natural disasters are the valid shock types)
        return "Conflict"

    def _evaluate_shock_type_rule(self, rule: str, raw_data: dict, alert_record: VariableData, level: str) -> bool:
        """Evaluate a shock type mapping rule."""
        try:
            # Simple rule evaluation (can be extended)
            # Format: "field_path==value" or "level==high" or "contains:keyword"

            if rule.startswith("level=="):
                target_level = rule.split("==")[1]
                return level == target_level

            elif "==" in rule:
                field_path, expected_value = rule.split("==", 1)
                field_value = self._get_field_value(raw_data, field_path, alert_record)
                return str(field_value) == expected_value

            elif rule.startswith("contains:"):
                keyword = rule.split(":", 1)[1]
                text_content = self._extract_text_content(raw_data, alert_record)
                return keyword.lower() in text_content.lower()

            return False

        except Exception:
            return False

    def _extract_relevant_fields(self, raw_data: dict) -> dict:
        """Extract relevant fields for detection data."""
        relevant = {}

        # Extract fields mentioned in scoring configuration
        for field_path in self.field_scores.keys():
            if "." in field_path or "[" in field_path:
                # Use simplified field name for storage
                simple_name = field_path.split(".")[-1].split("[")[0]
            else:
                simple_name = field_path

            field_value = self._get_field_value(raw_data, field_path, None)
            if field_value is not None:
                relevant[simple_name] = field_value

        return relevant

    def _detect_alert_clusters(self, scored_alerts: list[dict]) -> list[dict]:
        """Detect clusters of alerts in time and space."""
        if not self.enable_clustering or len(scored_alerts) < self.cluster_min_alerts:
            return []

        cluster_detections = []

        # Group by location
        location_groups = {}
        for alert_data in scored_alerts:
            alert_record = alert_data["alert_record"]
            if alert_record.gid:
                location_id = alert_record.gid.id
                if location_id not in location_groups:
                    location_groups[location_id] = []
                location_groups[location_id].append(alert_data)

        # Find temporal clusters within each location
        for location_id, location_alerts in location_groups.items():
            if len(location_alerts) >= self.cluster_min_alerts:
                clusters = self._find_temporal_clusters(location_alerts)
                for cluster in clusters:
                    detection = self._create_cluster_detection(cluster, location_id)
                    if detection:
                        cluster_detections.append(detection)

        return cluster_detections

    def _find_temporal_clusters(self, alerts: list[dict]) -> list[list[dict]]:
        """Find temporal clusters within alerts."""
        if len(alerts) < self.cluster_min_alerts:
            return []

        # Sort by timestamp
        sorted_alerts = sorted(alerts, key=lambda x: x["alert_record"].start_date)
        clusters = []
        current_cluster = [sorted_alerts[0]]

        for i in range(1, len(sorted_alerts)):
            prev_date = sorted_alerts[i - 1]["alert_record"].start_date
            curr_date = sorted_alerts[i]["alert_record"].start_date

            # Check if within cluster window
            if (curr_date - prev_date).total_seconds() / 3600 <= self.cluster_window_hours:
                current_cluster.append(sorted_alerts[i])
            else:
                # End current cluster if it meets minimum size
                if len(current_cluster) >= self.cluster_min_alerts:
                    clusters.append(current_cluster)
                current_cluster = [sorted_alerts[i]]

        # Don't forget the last cluster
        if len(current_cluster) >= self.cluster_min_alerts:
            clusters.append(current_cluster)

        return clusters

    def _create_cluster_detection(self, cluster: list[dict], location_id: int) -> dict | None:
        """Create detection from alert cluster."""
        try:
            location = Location.objects.get(id=location_id)

            # Calculate cluster metrics
            total_score = sum(alert["score"] for alert in cluster)
            avg_score = total_score / len(cluster)
            max_level = max(alert["level"] for alert in cluster if alert["level"] != "none")

            # Use earliest timestamp
            earliest_alert = min(cluster, key=lambda x: x["alert_record"].start_date)

            detection = {
                "detection_timestamp": timezone.make_aware(datetime.combine(earliest_alert["alert_record"].start_date, datetime.min.time())),
                "locations": [location],
                "confidence_score": min(avg_score / 20.0, 1.0),
                "shock_type_name": f"Alert Cluster - {max_level.title()}",
                "detection_data": {
                    "cluster_size": len(cluster),
                    "total_score": total_score,
                    "average_score": avg_score,
                    "max_level": max_level,
                    "alert_ids": [alert["alert_record"].id for alert in cluster],
                    "time_span_hours": (max(alert["alert_record"].start_date for alert in cluster) - min(alert["alert_record"].start_date for alert in cluster)).total_seconds()
                    / 3600,
                    "source": f"{self.__class__.__name__}_cluster",
                },
            }

            return detection

        except Location.DoesNotExist:
            self.logger.error(f"Location {location_id} not found")
            return None
        except Exception as e:
            self.logger.error(f"Error creating cluster detection: {str(e)}")
            return None

    def _generate_default_alert(self, detection: "Detection") -> dict:
        """Override to use detection title and data from Dataminr alerts."""
        from django.utils import timezone

        # Use the detection title (which contains the Dataminr headline)
        title = detection.title

        # Build descriptive text from detection data
        detection_data = detection.detection_data or {}
        score = detection_data.get("score", 0)
        level = detection_data.get("alert_level", "unknown")

        location_names = [loc.name for loc in detection.locations.all()]
        location_text = ", ".join(location_names) if location_names else "Unknown location"

        text = f"{title}\n\n"
        text += f"Location: {location_text}\n"
        text += f"Alert Level: {level.title()}\n"
        text += f"Score: {score:.1f}\n"
        text += f"Detection Date: {detection.detection_timestamp.strftime('%Y-%m-%d')}\n"

        if detection.confidence_score:
            text += f"Confidence: {detection.confidence_score:.1%}\n"

        # Add score components if available
        components = detection_data.get("score_components", {})
        if components:
            text += f"\nScore breakdown:\n"
            if components.get("field_scores"):
                text += f"  - Field scores: {components['field_scores']}\n"
            if components.get("keyword_score"):
                text += f"  - Keyword score: {components['keyword_score']}\n"
            if components.get("location_multiplier"):
                text += f"  - Location multiplier: {components['location_multiplier']}\n"

        return {
            "title": title,
            "text": text,
            "shock_type": detection.shock_type.id if detection.shock_type else None,
            "shock_date": detection.detection_timestamp.date(),
            "locations": [loc.id for loc in detection.locations.all()],
            "severity": self._calculate_severity(detection),
            "data_source": self._get_data_source_reference(detection),
            "valid_from": timezone.now(),
            "valid_until": self._calculate_validity_period(detection),
        }

    def get_configuration_schema(self) -> dict:
        """Return JSON schema for configuration validation."""
        return {
            "type": "object",
            "properties": {
                "variable_code": {"type": "string", "description": "Variable code to filter data"},
                "source_name": {"type": "string", "description": "Source name to filter data"},
                "field_scores": {
                    "type": "object",
                    "description": "Field-based scoring rules",
                    "patternProperties": {
                        ".*": {
                            "type": "object",
                            "description": "Scoring rules for a field",
                            "properties": {"exact_match": {"type": "object"}, "contains": {"type": "object"}, "regex": {"type": "object"}, "numeric": {"type": "object"}},
                        }
                    },
                },
                "keyword_scores": {"type": "object", "description": "Keyword scoring weights", "patternProperties": {".*": {"type": "number", "minimum": 0}}},
                "keyword_max_mode": {"type": "boolean", "description": "Use max instead of sum for keyword scores", "default": False},
                "text_fields": {"type": "array", "description": "Fields to extract text content from", "items": {"type": "string"}, "default": ["headline", "text_fallback"]},
                "location_multipliers": {"type": "object", "description": "Location-based score multipliers", "patternProperties": {".*": {"type": "number", "minimum": 0}}},
                "location_fields": {
                    "type": "array",
                    "description": "Fields to extract location from",
                    "items": {"type": "string"},
                    "default": ["estimatedEventLocation[0]", "location_fallback"],
                },
                "thresholds": {
                    "type": "object",
                    "properties": {
                        "critical": {"type": "number", "minimum": 0},
                        "high": {"type": "number", "minimum": 0},
                        "medium": {"type": "number", "minimum": 0},
                        "low": {"type": "number", "minimum": 0},
                    },
                },
                "min_detection_score": {"type": "number", "minimum": 0},
                "base_score": {"type": "number", "minimum": 0, "default": 1.0},
                "enable_clustering": {"type": "boolean", "default": False},
                "cluster_window_hours": {"type": "number", "minimum": 0},
                "cluster_min_alerts": {"type": "integer", "minimum": 2},
                "shock_type_mapping": {"type": "object", "description": "Rules for mapping alerts to shock types", "patternProperties": {".*": {"type": "string"}}},
            },
        }

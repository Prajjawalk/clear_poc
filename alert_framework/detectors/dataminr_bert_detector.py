"""Dataminr BERT detector for headline classification using fine-tuned model."""

import logging
from datetime import datetime, time
from typing import Any

import torch
from django.utils import timezone
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from alert_framework.base_detector import BaseDetector

logger = logging.getLogger(__name__)

# Global model cache to prevent loading model multiple times per worker process
# This is crucial for memory efficiency - the model (~500MB) is loaded once per worker
_MODEL_CACHE = {}


class DataminrBertDetector(BaseDetector):
    """Detector that classifies Dataminr headlines using fine-tuned BERT model."""

    def __init__(self, detector_config):
        """Initialize Dataminr BERT detector.

        Args:
            detector_config: Detector model instance with configuration
        """
        super().__init__(detector_config)
        self.model = None
        self.tokenizer = None
        self._load_config()
        self._load_model()

    def _load_config(self, **config):
        """Initialize the detector configuration."""
        # Get configuration from the detector model
        config_dict = self.config.configuration or {}
        config_dict.update(config)

        # BERT model configuration
        self.model_path = config_dict.get("model_path")
        if not self.model_path:
            raise ValueError("model_path is required in configuration")

        self.variable_code = config_dict.get("variable_code")
        if not self.variable_code:
            raise ValueError("variable_code is required in configuration")

        self.admin_level = config_dict.get("admin_level", None)
        self.confidence_threshold = config_dict.get("confidence_threshold", 0.5)
        self.max_length = config_dict.get("max_length", 64)
        self.batch_size = config_dict.get("batch_size", 8)

        # Field mapping for the headline text
        self.headline_field = config_dict.get("headline_field", "value")

        # Shock type mapping (similar to scoring detector)
        self.shock_type_mapping = config_dict.get("shock_type_mapping", {})

    def _load_model(self):
        """Load the fine-tuned BERT model and tokenizer.

        Uses a global cache to ensure the model is only loaded once per worker process,
        preventing excessive memory usage when multiple detector instances are created.
        """
        try:
            import os

            # Support relative paths from the detector file location
            if not os.path.isabs(self.model_path):
                # Relative path - resolve relative to this detector file
                detector_dir = os.path.dirname(os.path.abspath(__file__))
                resolved_path = os.path.join(detector_dir, self.model_path)
            else:
                resolved_path = self.model_path

            # Check if model is already cached for this path
            if resolved_path in _MODEL_CACHE:
                self.log_detection(
                    "Using cached BERT model",
                    level="info",
                    model_path=resolved_path,
                )
                self.tokenizer = _MODEL_CACHE[resolved_path]["tokenizer"]
                self.model = _MODEL_CACHE[resolved_path]["model"]
            else:
                self.log_detection(
                    "Loading BERT model into cache",
                    level="info",
                    model_path=resolved_path,
                )
                self.tokenizer = AutoTokenizer.from_pretrained(resolved_path)
                self.model = AutoModelForSequenceClassification.from_pretrained(resolved_path)
                self.model.eval()  # Set to evaluation mode

                # Cache the model for reuse in this worker process
                _MODEL_CACHE[resolved_path] = {
                    "tokenizer": self.tokenizer,
                    "model": self.model,
                }

                self.log_detection("BERT model loaded and cached successfully", level="info")
        except Exception as e:
            self.logger.error(f"Failed to load BERT model: {str(e)}")
            raise

    def _load_data(self, start_date=None, end_date=None):
        """Load data from the configured data source.

        Args:
            start_date: Start date for data retrieval
            end_date: End date for data retrieval

        Returns:
            QuerySet of VariableData records
        """
        if not self.variable_code:
            self.logger.warning("No variable_code configured for DataminrBertDetector")
            return None

        return self.get_variable_data(
            variable_code=self.variable_code,
            start_date=start_date,
            end_date=end_date,
            admin_level=self.admin_level,
        )

    def _classify_headlines(self, headlines: list[str]) -> tuple[list[int], list[float]]:
        """Classify headlines using BERT model.

        Args:
            headlines: List of headline texts

        Returns:
            Tuple of (predictions, probabilities) where predictions are 0/1
            and probabilities are confidence scores for class 1 (alert)
        """
        if not headlines:
            return [], []

        # Tokenize
        inputs = self.tokenizer(headlines, truncation=True, padding="max_length", max_length=self.max_length, return_tensors="pt")

        # Predict
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)
            predictions = logits.argmax(dim=-1).numpy().tolist()
            probabilities = probs[:, 1].numpy().tolist()  # Probability of class 1 (alert)

        return predictions, probabilities

    def detect(self, start_date: datetime, end_date: datetime, **kwargs) -> list[dict[str, Any]]:
        """Classify Dataminr headlines and return detections for alerts.

        Args:
            start_date: Analysis window start
            end_date: Analysis window end
            **kwargs: Additional parameters

        Returns:
            List of detection dictionaries for headlines classified as alerts
        """
        self.log_detection(
            "Starting Dataminr BERT detection",
            start_date=start_date,
            end_date=end_date,
            variable_code=self.variable_code,
            confidence_threshold=self.confidence_threshold,
        )

        # Load data for the specified time window
        data = self._load_data(start_date=start_date, end_date=end_date)

        if not data:
            self.log_detection("No data found for Dataminr BERT detection", level="warning")
            return []

        detections = []
        data_count = data.count()

        self.log_detection(f"Processing {data_count} headlines for classification")

        # Process in batches
        records_list = list(data)
        for i in range(0, len(records_list), self.batch_size):
            batch_records = records_list[i : i + self.batch_size]

            # Extract headlines
            headlines = []
            for record in batch_records:
                headline = None

                # Try to get headline based on field configuration
                if self.headline_field == "raw_data_headline":
                    # Extract from raw_data
                    if record.raw_data and isinstance(record.raw_data, dict):
                        headline = record.raw_data.get("headline")
                elif self.headline_field == "text":
                    # Use text field
                    headline = record.text
                else:
                    # Try to get from record attribute
                    headline = getattr(record, self.headline_field, None)

                # Fallback to text field if no headline found
                if not headline and record.text:
                    headline = record.text

                if not headline:
                    self.logger.warning(f"No headline found for record {record.id}")
                    headline = ""

                headlines.append(str(headline))

            # Classify batch
            predictions, probabilities = self._classify_headlines(headlines)

            # Create detections for alerts
            for record, prediction, probability in zip(batch_records, predictions, probabilities, strict=False):
                # Only create detection if classified as alert (1) and meets confidence threshold
                if prediction == 1 and probability >= self.confidence_threshold:
                    locations = []
                    if record.gid:
                        locations = [record.gid]

                    # Convert date to timezone-aware datetime if needed
                    detection_timestamp = record.start_date
                    if isinstance(detection_timestamp, datetime):
                        if timezone.is_naive(detection_timestamp):
                            detection_timestamp = timezone.make_aware(detection_timestamp)
                    else:
                        # Convert date to datetime at midnight in the current timezone
                        detection_timestamp = timezone.make_aware(datetime.combine(detection_timestamp, time.min))

                    # Get headline text (same logic as extraction above)
                    if self.headline_field == "raw_data_headline":
                        headline = record.raw_data.get("headline", "") if record.raw_data else ""
                    elif self.headline_field == "text":
                        headline = record.text or ""
                    else:
                        headline = getattr(record, self.headline_field, "")

                    if not headline and record.text:
                        headline = record.text

                    # Determine shock type using the mapping (similar to scoring detector)
                    shock_type_name = self._determine_shock_type(record, headline)

                    # Create title from headline (truncate to 200 chars for title field)
                    title = headline[:200] if headline else f"BERT Alert - {record.start_date.strftime('%Y-%m-%d')}"

                    detection = {
                        "title": title,
                        "detection_timestamp": detection_timestamp,
                        "locations": locations,
                        "confidence_score": probability,
                        "shock_type_name": shock_type_name,
                        "detection_data": {
                            "variable_code": record.variable.code,
                            "variable_name": record.variable.name,
                            "headline": headline,
                            "bert_prediction": prediction,
                            "bert_confidence": probability,
                            "confidence_threshold": self.confidence_threshold,
                            "start_date": record.start_date.isoformat() if record.start_date else None,
                            "end_date": record.end_date.isoformat() if record.end_date else None,
                            "location_name": record.gid.name if record.gid else None,
                            "admin_level": record.adm_level.code if record.adm_level else None,
                            "detector_type": "dataminr_bert",
                            "model_path": self.model_path,
                        },
                    }
                    detections.append(detection)

        self.log_detection(
            "Dataminr BERT detection completed",
            total_detections=len(detections),
            data_points_processed=data_count,
            detection_rate=f"{len(detections) / data_count * 100:.1f}%" if data_count > 0 else "0%",
        )

        return detections

    def _determine_shock_type(self, alert_record, headline: str) -> str:
        """Determine shock type based on configuration and alert content.

        Uses the same mapping logic as the scoring detector.

        Args:
            alert_record: VariableData record
            headline: The headline text

        Returns:
            Shock type name
        """
        raw_data = alert_record.raw_data or {}

        # Use configured shock type mapping
        for mapping_rule, shock_type in self.shock_type_mapping.items():
            if self._evaluate_shock_type_rule(mapping_rule, raw_data, alert_record, headline):
                return shock_type

        # Default fallback - use "Conflict" as the most common type for Dataminr alerts
        return "Conflict"

    def _evaluate_shock_type_rule(self, rule: str, raw_data: dict, alert_record, headline: str) -> bool:
        """Evaluate a shock type mapping rule.

        Supports rules like:
        - "alertTopics==Conflicts - Air": Check if field equals value
        - "contains:keyword": Check if keyword is in headline/text

        Args:
            rule: The mapping rule to evaluate
            raw_data: Raw data dictionary from the record
            alert_record: VariableData record
            headline: The headline text

        Returns:
            True if the rule matches
        """
        try:
            if "==" in rule:
                # Field equality check: "field==value"
                field_path, expected_value = rule.split("==", 1)
                field_value = self._get_field_value(raw_data, field_path, alert_record)

                # Handle array fields (e.g., alertTopics)
                if isinstance(field_value, list):
                    # Check if any item in the array matches
                    for item in field_value:
                        if isinstance(item, dict) and "name" in item:
                            if item["name"] == expected_value:
                                return True
                        elif str(item) == expected_value:
                            return True
                    return False
                else:
                    return str(field_value) == expected_value

            elif rule.startswith("contains:"):
                # Text contains check: "contains:keyword"
                keyword = rule.split(":", 1)[1]
                text_content = headline.lower() if headline else ""
                return keyword.lower() in text_content

            return False

        except Exception as e:
            self.logger.debug(f"Error evaluating shock type rule '{rule}': {str(e)}")
            return False

    def _get_field_value(self, raw_data: dict, field_path: str, alert_record) -> Any:
        """Extract field value using dot notation and array indexing.

        Args:
            raw_data: Raw data dictionary
            field_path: Field path (e.g., "alertTopics", "field.subfield", "array[0]")
            alert_record: VariableData record

        Returns:
            Field value or None if not found
        """
        try:
            # Handle special fallback fields
            if field_path == "text_fallback":
                return alert_record.text or ""
            elif field_path == "location_fallback":
                return alert_record.original_location_text or ""

            # Handle field path that exists directly in raw_data
            if field_path in raw_data:
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

    def get_configuration_schema(self) -> dict[str, Any]:
        """Return JSON schema for Dataminr BERT detector configuration.

        Returns:
            Dictionary containing the JSON schema
        """
        return {
            "type": "object",
            "properties": {
                "model_path": {
                    "type": "string",
                    "description": "Path to fine-tuned BERT model directory",
                    "minLength": 1,
                },
                "variable_code": {
                    "type": "string",
                    "description": "Code of the variable containing Dataminr headlines",
                    "minLength": 1,
                },
                "admin_level": {
                    "type": ["integer", "null"],
                    "description": "Administrative level filter (optional)",
                    "minimum": 0,
                },
                "confidence_threshold": {
                    "type": "number",
                    "description": "Minimum confidence score to trigger detection (0-1)",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.5,
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum token length for BERT tokenization",
                    "minimum": 1,
                    "default": 64,
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Number of headlines to process in each batch",
                    "minimum": 1,
                    "default": 8,
                },
                "headline_field": {
                    "type": "string",
                    "description": "Field name containing the headline text",
                    "default": "value",
                },
                "shock_type_mapping": {
                    "type": "object",
                    "description": "Rules for mapping alerts to shock types",
                    "patternProperties": {".*": {"type": "string"}},
                },
            },
            "required": ["model_path", "variable_code"],
            "additionalProperties": False,
            "title": "Dataminr BERT Detector Configuration",
            "description": "Configuration for BERT-based headline classification detector for Dataminr data",
        }

    def _calculate_severity(self, detection) -> int:
        """Calculate severity based on BERT confidence score.

        Args:
            detection: Detection instance

        Returns:
            int: Severity level between 1 and 5
        """
        confidence = detection.confidence_score
        if confidence is not None:
            # Map confidence to severity (higher confidence = higher severity)
            if confidence >= 0.9:
                return 5
            elif confidence >= 0.8:
                return 4
            elif confidence >= 0.7:
                return 3
            elif confidence >= 0.6:
                return 2
            else:
                return 1
        return 3  # Default medium severity

    def _get_detector_specific_context(self, detection) -> dict[str, Any]:
        """Get Dataminr BERT-specific context for template rendering.

        Args:
            detection: Detection instance

        Returns:
            Dictionary of additional context variables
        """
        detection_data = detection.detection_data or {}
        return {
            "detector_type": "dataminr_bert",
            "headline": detection_data.get("headline"),
            "bert_confidence": detection_data.get("bert_confidence"),
            "model_path": detection_data.get("model_path"),
            "is_ml_detection": True,
        }

    def _get_data_source_reference(self, detection) -> str | None:
        """Get data source reference for alert attribution.

        Args:
            detection: Detection instance

        Returns:
            String identifying the data source
        """
        return "Dataminr (BERT Classification)"

    def _generate_default_alert(self, detection: "Detection") -> dict:
        """Override to use headline as alert title.

        Args:
            detection: Detection instance

        Returns:
            Dictionary with alert data using headline as title
        """
        # Use the detection title (which contains the Dataminr headline)
        title = detection.title

        # Build descriptive text from detection data
        detection_data = detection.detection_data or {}
        headline = detection_data.get("headline", "")
        bert_confidence = detection_data.get("bert_confidence", 0)

        location_names = [loc.name for loc in detection.locations.all()]
        location_text = ", ".join(location_names) if location_names else "Unknown location"

        text = f"{headline}\n\n"
        text += f"Location: {location_text}\n"
        text += f"Detection Date: {detection.detection_timestamp.strftime('%Y-%m-%d')}\n"

        if bert_confidence:
            text += f"BERT Confidence: {bert_confidence:.1%}\n"

        return {
            "title": title,
            "text": text,
            "shock_type": detection.shock_type.id if detection.shock_type else None,
            "shock_date": detection.detection_timestamp.date(),
            "locations": [loc.id for loc in detection.locations.all()],
            "severity": self._calculate_severity(detection),
            "data_source": self._get_data_source_reference(detection),
        }

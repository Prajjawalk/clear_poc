"""Tests for BERT detector implementation."""

import json
from datetime import datetime, time
from unittest.mock import MagicMock, Mock, patch

import torch
from django.test import TestCase
from django.utils import timezone

from alert_framework.detectors.dataminr_bert_detector import DataminrBertDetector
from alert_framework.models import Detector
from alerts.models import ShockType
from data_pipeline.models import Source, Variable, VariableData
from location.models import AdmLevel, Location


class DataminrBertDetectorTest(TestCase):
    """Test cases for DataminrBertDetector."""

    def setUp(self):
        """Set up test data."""
        # Create shock types
        self.shock_type_conflict = ShockType.objects.create(name="Conflict")
        self.shock_type_natural = ShockType.objects.create(name="Natural disasters")

        # Create source and variable
        self.source = Source.objects.create(
            name="Dataminr",
            type="api",
            class_name="data_pipeline.sources.dataminr.DataminrSource"
        )
        self.variable = Variable.objects.create(
            code="dataminr_alerts",
            name="Dataminr Alerts",
            source=self.source,
            type="qualitative",
            period="day",
            adm_level=1
        )

        # Create location structure
        self.admin_level = AdmLevel.objects.create(name="State", code="1")
        self.location = Location.objects.create(
            name="Al Fashir",
            geo_id="SD_ND_001",
            admin_level=self.admin_level
        )

        # Create test date
        self.test_date = datetime(2025, 10, 7).date()

    def _create_detector_config(self, config_overrides=None):
        """Helper to create detector configuration."""
        config = {
            "model_path": "/fake/model/path",
            "variable_code": "dataminr_alerts",
            "admin_level": 1,
            "confidence_threshold": 0.5,
            "max_length": 64,
            "batch_size": 8,
            "headline_field": "raw_data_headline",
            "shock_type_mapping": {
                "alertTopics==Conflicts - Air": "Conflict",
                "contains:flood": "Natural disasters"
            }
        }
        if config_overrides:
            config.update(config_overrides)

        return Detector.objects.create(
            name="Test BERT Detector",
            class_name="alert_framework.detectors.dataminr_bert_detector.DataminrBertDetector",
            active=True,
            configuration=config
        )

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_model_loading(self, mock_model_class, mock_tokenizer_class):
        """Test BERT model and tokenizer loading."""
        mock_tokenizer = Mock()
        mock_model = Mock()
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
        mock_model_class.from_pretrained.return_value = mock_model

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        # Verify model and tokenizer were loaded
        mock_tokenizer_class.from_pretrained.assert_called_once()
        mock_model_class.from_pretrained.assert_called_once()
        mock_model.eval.assert_called_once()
        self.assertEqual(detector.model, mock_model)
        self.assertEqual(detector.tokenizer, mock_tokenizer)

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_configuration_loading(self, mock_model_class, mock_tokenizer_class):
        """Test configuration loading and validation."""
        mock_tokenizer_class.from_pretrained.return_value = Mock()
        mock_model_class.from_pretrained.return_value = Mock()

        detector_config = self._create_detector_config({
            "confidence_threshold": 0.7,
            "max_length": 128,
            "batch_size": 16
        })
        detector = DataminrBertDetector(detector_config)

        self.assertEqual(detector.variable_code, "dataminr_alerts")
        self.assertEqual(detector.admin_level, 1)
        self.assertEqual(detector.confidence_threshold, 0.7)
        self.assertEqual(detector.max_length, 128)
        self.assertEqual(detector.batch_size, 16)

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_missing_required_config(self, mock_model_class, mock_tokenizer_class):
        """Test that missing required configuration raises error."""
        with self.assertRaises(ValueError) as context:
            detector_config = Detector.objects.create(
                name="Invalid BERT Detector",
                class_name="alert_framework.detectors.dataminr_bert_detector.DataminrBertDetector",
                active=True,
                configuration={"variable_code": "dataminr_alerts"}  # Missing model_path
            )
            DataminrBertDetector(detector_config)

        self.assertIn("model_path", str(context.exception))

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_headline_classification(self, mock_model_class, mock_tokenizer_class):
        """Test headline classification with BERT model."""
        # Mock tokenizer
        mock_tokenizer = Mock()
        mock_inputs = {"input_ids": torch.tensor([[1, 2, 3]]), "attention_mask": torch.tensor([[1, 1, 1]])}
        mock_tokenizer.return_value = mock_inputs
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer

        # Mock model outputs
        mock_model = Mock()
        mock_logits = torch.tensor([[0.3, 0.7]])  # Class 1 (alert) has higher score
        mock_outputs = Mock(logits=mock_logits)
        mock_model.return_value = mock_outputs
        mock_model_class.from_pretrained.return_value = mock_model

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        headlines = ["Armed conflict in Al Fashir"]
        predictions, probabilities = detector._classify_headlines(headlines)

        self.assertEqual(len(predictions), 1)
        self.assertEqual(len(probabilities), 1)
        self.assertEqual(predictions[0], 1)  # Predicted as alert
        self.assertGreater(probabilities[0], 0.5)  # High confidence

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_batch_classification(self, mock_model_class, mock_tokenizer_class):
        """Test classification of multiple headlines in batch."""
        mock_tokenizer = Mock()
        mock_tokenizer.return_value = {"input_ids": Mock(), "attention_mask": Mock()}
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer

        mock_model = Mock()
        # Mock 3 headlines with different predictions
        mock_logits = torch.tensor([[0.8, 0.2], [0.3, 0.7], [0.9, 0.1]])
        mock_outputs = Mock(logits=mock_logits)
        mock_model.return_value = mock_outputs
        mock_model_class.from_pretrained.return_value = mock_model

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        headlines = ["Headline 1", "Headline 2", "Headline 3"]
        predictions, probabilities = detector._classify_headlines(headlines)

        self.assertEqual(len(predictions), 3)
        self.assertEqual(predictions[0], 0)  # Not an alert
        self.assertEqual(predictions[1], 1)  # Is an alert
        self.assertEqual(predictions[2], 0)  # Not an alert

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_detect_with_data(self, mock_model_class, mock_tokenizer_class):
        """Test detection with actual VariableData records."""
        # Mock BERT model
        mock_tokenizer = Mock()
        mock_tokenizer.return_value = {"input_ids": Mock(), "attention_mask": Mock()}
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer

        mock_model = Mock()
        mock_logits = torch.tensor([[0.2, 0.8]])  # High confidence alert
        mock_outputs = Mock(logits=mock_logits)
        mock_model.return_value = mock_outputs
        mock_model_class.from_pretrained.return_value = mock_model

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        # Create test variable data
        raw_data = {
            "headline": "Armed conflict reported in Al Fashir",
            "alertTopics": [{"name": "Conflicts - Air"}]
        }
        VariableData.objects.create(
            variable=self.variable,
            gid=self.location,
            adm_level=self.admin_level,
            start_date=self.test_date,
            end_date=self.test_date,
            raw_data=raw_data,
            text="Armed conflict reported in Al Fashir"
        )

        start_date = datetime.combine(self.test_date, time.min)
        end_date = datetime.combine(self.test_date, time.max)

        detections = detector.detect(timezone.make_aware(start_date), timezone.make_aware(end_date))

        self.assertEqual(len(detections), 1)
        detection = detections[0]

        self.assertIn("Armed conflict", detection["title"])
        self.assertEqual(detection["shock_type_name"], "Conflict")
        self.assertGreater(detection["confidence_score"], 0.5)
        self.assertEqual(len(detection["locations"]), 1)
        self.assertEqual(detection["locations"][0], self.location)

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_confidence_threshold_filtering(self, mock_model_class, mock_tokenizer_class):
        """Test that only detections above confidence threshold are returned."""
        mock_tokenizer = Mock()
        mock_tokenizer.return_value = {"input_ids": Mock(), "attention_mask": Mock()}
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer

        mock_model = Mock()
        # Low confidence prediction (0.4 < 0.5 threshold)
        mock_logits = torch.tensor([[0.6, 0.4]])
        mock_outputs = Mock(logits=mock_logits)
        mock_model.return_value = mock_outputs
        mock_model_class.from_pretrained.return_value = mock_model

        detector_config = self._create_detector_config({"confidence_threshold": 0.5})
        detector = DataminrBertDetector(detector_config)

        # Create test data
        VariableData.objects.create(
            variable=self.variable,
            gid=self.location,
            adm_level=self.admin_level,
            start_date=self.test_date,
            end_date=self.test_date,
            raw_data={"headline": "Low confidence alert"},
            text="Low confidence alert"
        )

        start_date = datetime.combine(self.test_date, time.min)
        end_date = datetime.combine(self.test_date, time.max)

        detections = detector.detect(timezone.make_aware(start_date), timezone.make_aware(end_date))

        # Should be filtered out due to low confidence
        self.assertEqual(len(detections), 0)

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_shock_type_mapping(self, mock_model_class, mock_tokenizer_class):
        """Test shock type determination from mapping rules."""
        mock_tokenizer = Mock()
        mock_tokenizer.return_value = {"input_ids": Mock(), "attention_mask": Mock()}
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer

        mock_model = Mock()
        mock_logits = torch.tensor([[0.2, 0.8]])
        mock_outputs = Mock(logits=mock_logits)
        mock_model.return_value = mock_outputs
        mock_model_class.from_pretrained.return_value = mock_model

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        # Create data with flood keyword
        VariableData.objects.create(
            variable=self.variable,
            gid=self.location,
            adm_level=self.admin_level,
            start_date=self.test_date,
            end_date=self.test_date,
            raw_data={"headline": "Major flood disaster in Sudan"},
            text="Major flood disaster in Sudan"
        )

        start_date = datetime.combine(self.test_date, time.min)
        end_date = datetime.combine(self.test_date, time.max)

        detections = detector.detect(timezone.make_aware(start_date), timezone.make_aware(end_date))

        self.assertEqual(len(detections), 1)
        # Should be mapped to "Natural disasters" based on "contains:flood" rule
        self.assertEqual(detections[0]["shock_type_name"], "Natural disasters")

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_empty_data_handling(self, mock_model_class, mock_tokenizer_class):
        """Test handling of empty data."""
        mock_tokenizer_class.from_pretrained.return_value = Mock()
        mock_model_class.from_pretrained.return_value = Mock()

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        start_date = timezone.make_aware(datetime.combine(self.test_date, time.min))
        end_date = timezone.make_aware(datetime.combine(self.test_date, time.max))

        detections = detector.detect(start_date, end_date)

        self.assertEqual(len(detections), 0)

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_severity_calculation(self, mock_model_class, mock_tokenizer_class):
        """Test severity calculation based on confidence score."""
        mock_tokenizer_class.from_pretrained.return_value = Mock()
        mock_model_class.from_pretrained.return_value = Mock()

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        # Test different confidence levels
        mock_detection = Mock(confidence_score=0.95)
        self.assertEqual(detector._calculate_severity(mock_detection), 5)

        mock_detection.confidence_score = 0.85
        self.assertEqual(detector._calculate_severity(mock_detection), 4)

        mock_detection.confidence_score = 0.75
        self.assertEqual(detector._calculate_severity(mock_detection), 3)

        mock_detection.confidence_score = 0.65
        self.assertEqual(detector._calculate_severity(mock_detection), 2)

        mock_detection.confidence_score = 0.55
        self.assertEqual(detector._calculate_severity(mock_detection), 1)

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_configuration_schema(self, mock_model_class, mock_tokenizer_class):
        """Test configuration schema generation."""
        mock_tokenizer_class.from_pretrained.return_value = Mock()
        mock_model_class.from_pretrained.return_value = Mock()

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        schema = detector.get_configuration_schema()

        self.assertEqual(schema["type"], "object")
        self.assertIn("model_path", schema["properties"])
        self.assertIn("variable_code", schema["properties"])
        self.assertIn("confidence_threshold", schema["properties"])
        self.assertIn("model_path", schema["required"])
        self.assertIn("variable_code", schema["required"])

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_detector_specific_context(self, mock_model_class, mock_tokenizer_class):
        """Test detector-specific context for template rendering."""
        mock_tokenizer_class.from_pretrained.return_value = Mock()
        mock_model_class.from_pretrained.return_value = Mock()

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        mock_detection = Mock(
            detection_data={
                "headline": "Test headline",
                "bert_confidence": 0.87,
                "model_path": "/fake/model/path"
            }
        )

        context = detector._get_detector_specific_context(mock_detection)

        self.assertEqual(context["detector_type"], "dataminr_bert")
        self.assertEqual(context["headline"], "Test headline")
        self.assertEqual(context["bert_confidence"], 0.87)
        self.assertTrue(context["is_ml_detection"])

    @patch('alert_framework.detectors.dataminr_bert_detector.AutoTokenizer')
    @patch('alert_framework.detectors.dataminr_bert_detector.AutoModelForSequenceClassification')
    def test_data_source_reference(self, mock_model_class, mock_tokenizer_class):
        """Test data source reference for alert attribution."""
        mock_tokenizer_class.from_pretrained.return_value = Mock()
        mock_model_class.from_pretrained.return_value = Mock()

        detector_config = self._create_detector_config()
        detector = DataminrBertDetector(detector_config)

        mock_detection = Mock()
        source_ref = detector._get_data_source_reference(mock_detection)

        self.assertEqual(source_ref, "Dataminr (BERT Classification)")

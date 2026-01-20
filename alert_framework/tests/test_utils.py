"""Tests for alert framework utilities."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from django.test import TestCase

from alert_framework.utils import (
    build_detection_filters,
    calculate_time_ago,
    parse_date_filter,
    parse_detector_class_name,
    run_task_with_fallback,
    validate_action_request,
)


class UtilsTest(TestCase):
    """Test cases for utility functions."""

    def test_parse_detector_class_name(self):
        """Test detector class name parsing."""
        # Test full module path
        result = parse_detector_class_name("alert_framework.detectors.surge_detector.ConflictSurgeDetector")
        self.assertEqual(result, "ConflictSurgeDetector")

        # Test simple class name
        result = parse_detector_class_name("TestDetector")
        self.assertEqual(result, "TestDetector")

        # Test empty string
        result = parse_detector_class_name("")
        self.assertEqual(result, "Unknown")

        # Test None
        result = parse_detector_class_name(None)
        self.assertEqual(result, "Unknown")

    def test_calculate_time_ago(self):
        """Test time ago calculation."""
        # Test seconds
        delta = timedelta(seconds=30)
        result = calculate_time_ago(delta)
        self.assertEqual(result, "Just now")

        # Test 1 minute
        delta = timedelta(minutes=1)
        result = calculate_time_ago(delta)
        self.assertEqual(result, "1 minute ago")

        # Test multiple minutes
        delta = timedelta(minutes=5)
        result = calculate_time_ago(delta)
        self.assertEqual(result, "5 minutes ago")

        # Test 1 hour
        delta = timedelta(hours=1)
        result = calculate_time_ago(delta)
        self.assertEqual(result, "1 hour ago")

        # Test multiple hours
        delta = timedelta(hours=3)
        result = calculate_time_ago(delta)
        self.assertEqual(result, "3 hours ago")

        # Test 1 day
        delta = timedelta(days=1)
        result = calculate_time_ago(delta)
        self.assertEqual(result, "1 day ago")

        # Test multiple days
        delta = timedelta(days=5)
        result = calculate_time_ago(delta)
        self.assertEqual(result, "5 days ago")

    def test_parse_date_filter(self):
        """Test date filter parsing."""
        # Test valid ISO date
        date_string = "2023-12-01T10:30:00Z"
        result = parse_date_filter(date_string)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 1)

        # Test date with timezone
        date_string = "2023-12-01T10:30:00+05:00"
        result = parse_date_filter(date_string)
        self.assertIsInstance(result, datetime)

        # Test invalid date
        result = parse_date_filter("invalid-date")
        self.assertIsNone(result)

        # Test empty string
        result = parse_date_filter("")
        self.assertIsNone(result)

        # Test None
        result = parse_date_filter(None)
        self.assertIsNone(result)

    def test_build_detection_filters(self):
        """Test detection filter building."""
        # Test empty parameters
        result = build_detection_filters({})
        self.assertEqual(result, {})

        # Test detector filter
        params = {"detector": "123"}
        result = build_detection_filters(params)
        self.assertEqual(result, {"detector_id": "123"})

        # Test status filter
        params = {"status": "pending"}
        result = build_detection_filters(params)
        self.assertEqual(result, {"status": "pending"})

        # Test shock type filter
        params = {"shock_type": "456"}
        result = build_detection_filters(params)
        self.assertEqual(result, {"shock_type_id": "456"})

        # Test date range filters
        params = {"start_date": "2023-12-01T00:00:00Z", "end_date": "2023-12-31T23:59:59Z"}
        result = build_detection_filters(params)
        self.assertIn("detection_timestamp__gte", result)
        self.assertIn("detection_timestamp__lte", result)

        # Test confidence filter
        params = {"min_confidence": "0.8"}
        result = build_detection_filters(params)
        self.assertEqual(result, {"confidence_score__gte": 0.8})

        # Test invalid confidence filter
        params = {"min_confidence": "invalid"}
        result = build_detection_filters(params)
        self.assertEqual(result, {})

        # Test multiple filters
        params = {"detector": "123", "status": "pending", "min_confidence": "0.75"}
        result = build_detection_filters(params)
        expected = {"detector_id": "123", "status": "pending", "confidence_score__gte": 0.75}
        self.assertEqual(result, expected)

    def test_validate_action_request(self):
        """Test action request validation."""
        # Test valid POST request with required fields
        result = validate_action_request("POST", ["action", "id"], {"action": "process", "id": "123"})
        self.assertIsNone(result)

        # Test invalid method
        result = validate_action_request("GET", ["action"], {"action": "process"})
        self.assertEqual(result["error"], "POST method required")
        self.assertEqual(result["status"], 405)

        # Test missing required field
        result = validate_action_request("POST", ["action", "id"], {"action": "process"})
        self.assertEqual(result["error"], "id parameter required")
        self.assertEqual(result["status"], 400)

        # Test empty required fields list
        result = validate_action_request("POST", [], {"action": "process"})
        self.assertIsNone(result)


class RunTaskWithFallbackTest(TestCase):
    """Test cases for run_task_with_fallback function."""

    def setUp(self):
        """Set up test mocks."""
        self.mock_task = Mock()
        self.mock_task.delay = Mock()

    @patch("celery.current_app")
    def test_async_execution_with_workers(self, mock_current_app):
        """Test async execution when Celery workers are available."""
        # Mock successful Celery inspection
        mock_inspect = Mock()
        mock_inspect.active.return_value = {"worker1": []}  # Workers available
        mock_current_app.control.inspect.return_value = mock_inspect

        # Mock task result
        mock_task_result = Mock()
        mock_task_result.id = "task-123"
        self.mock_task.delay.return_value = mock_task_result

        result, mode = run_task_with_fallback(self.mock_task, "arg1", "arg2", task_name="Test Task", kwarg1="value1")

        self.assertEqual(mode, "async")
        self.assertEqual(result, mock_task_result)
        self.mock_task.delay.assert_called_once_with("arg1", "arg2", kwarg1="value1")

    @patch("celery.current_app")
    def test_sync_execution_no_workers(self, mock_current_app):
        """Test sync execution when no Celery workers are available."""
        # Mock Celery inspection with no workers
        mock_inspect = Mock()
        mock_inspect.active.return_value = {}  # No workers
        mock_current_app.control.inspect.return_value = mock_inspect

        # Mock sync task execution
        self.mock_task.return_value = "sync_result"

        result, mode = run_task_with_fallback(self.mock_task, "arg1", "arg2", task_name="Test Task", kwarg1="value1")

        self.assertEqual(mode, "sync")
        self.assertEqual(result, "sync_result")
        self.mock_task.assert_called_once_with("arg1", "arg2", kwarg1="value1")

    @patch("celery.current_app")
    def test_sync_execution_inspection_fails(self, mock_current_app):
        """Test sync execution when Celery inspection fails."""
        # Mock Celery inspection failure
        mock_current_app.control.inspect.side_effect = Exception("Inspection failed")

        # Mock sync task execution
        self.mock_task.return_value = "sync_result"

        result, mode = run_task_with_fallback(self.mock_task, "arg1", "arg2", task_name="Test Task")

        self.assertEqual(mode, "sync-error")
        self.assertEqual(result, "sync_result")

    @patch("builtins.__import__")
    def test_sync_execution_no_celery(self, mock_import):
        """Test sync execution when Celery is not available."""
        # Mock import to raise ImportError for celery
        def side_effect(name, *args, **kwargs):
            if name == "celery":
                raise ImportError("Celery not available")
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = side_effect

        # Mock sync task execution
        self.mock_task.return_value = "sync_result"

        result, mode = run_task_with_fallback(self.mock_task, "arg1", "arg2", task_name="Test Task")

        self.assertEqual(mode, "sync")
        self.assertEqual(result, "sync_result")

    @patch("celery.current_app")
    def test_task_without_delay_method(self, mock_current_app):
        """Test handling of tasks without delay method."""
        # Mock successful Celery inspection
        mock_inspect = Mock()
        mock_inspect.active.return_value = {"worker1": []}
        mock_current_app.control.inspect.return_value = mock_inspect

        # Create a mock task without delay method
        mock_task_no_delay = Mock()
        mock_task_no_delay.delay.side_effect = AttributeError("No delay method")
        mock_task_no_delay.return_value = "sync_result"

        result, mode = run_task_with_fallback(mock_task_no_delay, "arg1", task_name="Test Task")

        # Should fall back to sync execution
        self.assertEqual(mode, "sync-error")
        self.assertEqual(result, "sync_result")

    @patch("celery.current_app")
    def test_task_result_without_id(self, mock_current_app):
        """Test handling task results without ID attribute."""
        # Mock successful Celery inspection
        mock_inspect = Mock()
        mock_inspect.active.return_value = {"worker1": []}
        mock_current_app.control.inspect.return_value = mock_inspect

        # Mock task result without ID
        mock_task_result = Mock(spec=[])  # No attributes
        self.mock_task.delay.return_value = mock_task_result

        result, mode = run_task_with_fallback(self.mock_task, task_name="Test Task")

        self.assertEqual(mode, "async")
        self.assertEqual(result, mock_task_result)

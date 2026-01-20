"""Unit tests for task monitoring models."""

import logging
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from data_pipeline.models import Source, Variable
from location.models import AdmLevel, Location
from task_monitoring.models import TaskExecution, TaskType, TaskLog


class TaskTypeModelTests(TestCase):
    """Tests for TaskType model."""

    def setUp(self):
        """Set up test data."""
        self.task_type = TaskType.objects.create(name="test_task")

    def test_task_type_creation(self):
        """Test TaskType model creation."""
        self.assertEqual(self.task_type.name, "test_task")
        self.assertTrue(self.task_type.created_at)
        self.assertTrue(self.task_type.updated_at)
        self.assertEqual(str(self.task_type), "test_task")

    def test_task_type_ordering(self):
        """Test TaskType ordering by name."""
        TaskType.objects.create(name="zebra_task")
        TaskType.objects.create(name="alpha_task")

        task_types = list(TaskType.objects.all())
        names = [tt.name for tt in task_types]

        self.assertEqual(names, ["alpha_task", "test_task", "zebra_task"])

    def test_task_type_unique_name(self):
        """Test that TaskType names must be unique."""
        with self.assertRaises(Exception):
            TaskType.objects.create(name="test_task")

    def test_task_type_max_length(self):
        """Test TaskType name max length validation."""
        long_name = "x" * 256
        with self.assertRaises(ValidationError):
            task_type = TaskType(name=long_name)
            task_type.full_clean()


class TaskExecutionModelTests(TestCase):
    """Tests for TaskExecution model."""

    def setUp(self):
        """Set up test data."""
        self.task_type = TaskType.objects.create(name="test_task")

        # Create related data pipeline objects
        self.source = Source.objects.create(name="Test Source", type="api", class_name="TestSource")

        self.variable = Variable.objects.create(
            source=self.source,
            name="Test Variable",
            code="test_var",
            period="day",
            adm_level=0,
            type="quantitative",
        )

    def test_task_execution_creation(self):
        """Test TaskExecution model creation."""
        execution = TaskExecution.objects.create(task_id="test-123", task_type=self.task_type, status="pending")

        self.assertEqual(execution.task_id, "test-123")
        self.assertEqual(execution.task_type, self.task_type)
        self.assertEqual(execution.status, "pending")
        self.assertEqual(execution.retry_count, 0)
        self.assertEqual(execution.max_retries, 3)
        self.assertTrue(execution.created_at)
        self.assertTrue(execution.updated_at)

    def test_task_execution_str(self):
        """Test TaskExecution string representation."""
        execution = TaskExecution.objects.create(task_id="test-123", task_type=self.task_type, status="success")

        expected = "test_task - test-123 (success)"
        self.assertEqual(str(execution), expected)

    def test_task_execution_with_relationships(self):
        """Test TaskExecution with related source and variable."""
        execution = TaskExecution.objects.create(
            task_id="test-456",
            task_type=self.task_type,
            source=self.source,
            variable=self.variable,
            arg1=123,
        )

        self.assertEqual(execution.source, self.source)
        self.assertEqual(execution.variable, self.variable)
        self.assertEqual(execution.arg1, 123)

    def test_duration_seconds_property(self):
        """Test duration_seconds property calculation."""
        start_time = timezone.now()
        end_time = start_time + timedelta(seconds=30)

        execution = TaskExecution.objects.create(
            task_id="test-789",
            task_type=self.task_type,
            started_at=start_time,
            completed_at=end_time,
        )

        self.assertEqual(execution.duration_seconds, 30.0)

    def test_duration_seconds_property_incomplete(self):
        """Test duration_seconds property when task is incomplete."""
        execution = TaskExecution.objects.create(
            task_id="test-incomplete",
            task_type=self.task_type,
            started_at=timezone.now(),
        )

        self.assertIsNone(execution.duration_seconds)

    def test_is_completed_property(self):
        """Test is_completed property."""
        success_execution = TaskExecution.objects.create(task_id="test-success", task_type=self.task_type, status="success")

        failure_execution = TaskExecution.objects.create(task_id="test-failure", task_type=self.task_type, status="failure")

        pending_execution = TaskExecution.objects.create(task_id="test-pending", task_type=self.task_type, status="pending")

        self.assertTrue(success_execution.is_completed)
        self.assertTrue(failure_execution.is_completed)
        self.assertFalse(pending_execution.is_completed)

    def test_can_retry_property(self):
        """Test can_retry property."""
        # Can retry: failure with retries remaining
        can_retry_execution = TaskExecution.objects.create(
            task_id="test-can-retry",
            task_type=self.task_type,
            status="failure",
            retry_count=1,
            max_retries=3,
        )

        # Cannot retry: success
        success_execution = TaskExecution.objects.create(task_id="test-success", task_type=self.task_type, status="success")

        # Cannot retry: max retries exceeded
        max_retries_execution = TaskExecution.objects.create(
            task_id="test-max-retries",
            task_type=self.task_type,
            status="failure",
            retry_count=3,
            max_retries=3,
        )

        self.assertTrue(can_retry_execution.can_retry)
        self.assertFalse(success_execution.can_retry)
        self.assertFalse(max_retries_execution.can_retry)

    def test_task_execution_unique_task_id(self):
        """Test that task_id must be unique."""
        TaskExecution.objects.create(task_id="unique-test", task_type=self.task_type)

        with self.assertRaises(Exception):
            TaskExecution.objects.create(task_id="unique-test", task_type=self.task_type)

    def test_task_execution_ordering(self):
        """Test TaskExecution ordering by created_at descending."""
        # Create executions with slight delays
        first = TaskExecution.objects.create(task_id="first", task_type=self.task_type)

        second = TaskExecution.objects.create(task_id="second", task_type=self.task_type)

        executions = list(TaskExecution.objects.all())
        self.assertEqual(executions[0], second)  # Most recent first
        self.assertEqual(executions[1], first)

    def test_task_execution_json_result(self):
        """Test TaskExecution with JSON result data."""
        result_data = {"records_processed": 100, "errors": [], "summary": "Success"}

        execution = TaskExecution.objects.create(
            task_id="test-json",
            task_type=self.task_type,
            result=result_data,
            status="success",
        )

        self.assertEqual(execution.result, result_data)
        self.assertEqual(execution.result["records_processed"], 100)


class TaskMonitoringModelRelationshipTests(TestCase):
    """Tests for model relationships and foreign keys."""

    def setUp(self):
        """Set up test data with relationships."""
        # Create location data for foreign key relationships
        self.admin_level = AdmLevel.objects.create(code="1", name="Admin1")
        self.location = Location.objects.create(geo_id="SD_001", name="Khartoum", admin_level=self.admin_level)

        self.source = Source.objects.create(name="Test Source", type="api", class_name="TestSource")

        self.variable = Variable.objects.create(
            source=self.source,
            name="Test Var",
            code="test_var",
            period="day",
            adm_level=0,
            type="quantitative",
        )

        self.task_type = TaskType.objects.create(name="test_task")

    def test_task_execution_cascade_relationships(self):
        """Test cascade behavior for TaskExecution relationships."""
        execution = TaskExecution.objects.create(
            task_id="test-cascade",
            task_type=self.task_type,
            source=self.source,
            variable=self.variable,
        )

        # Test source cascade delete
        self.source.delete()

        # TaskExecution should be deleted due to CASCADE
        with self.assertRaises(TaskExecution.DoesNotExist):
            TaskExecution.objects.get(id=execution.id)

    def test_task_execution_protect_relationships(self):
        """Test PROTECT behavior for TaskExecution-TaskType relationship."""
        TaskExecution.objects.create(task_id="test-protect", task_type=self.task_type)

        # Should not be able to delete TaskType due to PROTECT
        with self.assertRaises(Exception):
            self.task_type.delete()

    def test_related_manager_access(self):
        """Test accessing related objects through managers."""
        # Create multiple executions for same task type
        exec1 = TaskExecution.objects.create(task_id="rel-1", task_type=self.task_type, status="success")

        exec2 = TaskExecution.objects.create(task_id="rel-2", task_type=self.task_type, status="failure")

        # Test reverse relationship access
        executions = self.task_type.executions.all()
        self.assertEqual(len(executions), 2)
        self.assertIn(exec1, executions)
        self.assertIn(exec2, executions)

        # Test filtering through relationship
        successful = self.task_type.executions.filter(status="success")
        self.assertEqual(len(successful), 1)
        self.assertEqual(successful[0], exec1)


class TaskLogModelTests(TestCase):
    """Tests for TaskLog model."""

    def setUp(self):
        """Set up test data."""
        self.test_task_id = str(uuid.uuid4())

    def test_task_log_creation(self):
        """Test TaskLog model creation."""
        log = TaskLog.objects.create(
            task_id=self.test_task_id,
            level=logging.INFO,
            level_name="INFO",
            message="Test log message",
            module="test_module",
            function_name="test_function",
            line_number=42,
            thread=12345,
            process=67890,
        )

        self.assertEqual(log.task_id, self.test_task_id)
        self.assertEqual(log.level, logging.INFO)
        self.assertEqual(log.level_name, "INFO")
        self.assertEqual(log.message, "Test log message")
        self.assertEqual(log.module, "test_module")
        self.assertEqual(log.function_name, "test_function")
        self.assertEqual(log.line_number, 42)
        self.assertEqual(log.thread, 12345)
        self.assertEqual(log.process, 67890)
        self.assertTrue(log.timestamp)

    def test_task_log_str_representation(self):
        """Test TaskLog string representation."""
        log = TaskLog.objects.create(task_id=self.test_task_id, level=logging.ERROR, level_name="ERROR", message="Test error message")

        # The actual __str__ method shows: "timestamp [LEVEL] task_id: message"
        str_repr = str(log)
        self.assertIn("ERROR", str_repr)
        self.assertIn(self.test_task_id, str_repr)
        self.assertIn("Test error message", str_repr)

    def test_task_log_level_choices(self):
        """Test TaskLog level choices."""
        levels = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level_num, level_name in levels:
            log = TaskLog.objects.create(task_id=self.test_task_id + f"_{level_name}", level=level_num, level_name=level_name, message=f"Test {level_name} message")

            self.assertEqual(log.level, level_num)
            self.assertEqual(log.level_name, level_name)

    def test_task_log_level_color_property(self):
        """Test level_color property for different log levels."""
        test_cases = [
            (logging.DEBUG, "secondary"),
            (logging.INFO, "info"),
            (logging.WARNING, "warning"),
            (logging.ERROR, "danger"),
            (logging.CRITICAL, "danger"),
            (99, "secondary"),  # Unknown level
        ]

        for level, expected_color in test_cases:
            log = TaskLog.objects.create(task_id=f"{self.test_task_id}_{level}", level=level, level_name="TEST", message="Test message")

            self.assertEqual(log.level_color, expected_color)

    def test_task_log_level_icon_property(self):
        """Test level_icon property for different log levels."""
        test_cases = [
            (logging.DEBUG, "bug"),
            (logging.INFO, "info-circle"),
            (logging.WARNING, "exclamation-triangle"),
            (logging.ERROR, "x-circle"),
            (logging.CRITICAL, "x-octagon"),
            (99, "info-circle"),  # Unknown level (default)
        ]

        for level, expected_icon in test_cases:
            log = TaskLog.objects.create(task_id=f"{self.test_task_id}_{level}", level=level, level_name="TEST", message="Test message")

            self.assertEqual(log.level_icon, expected_icon)

    def test_task_log_ordering(self):
        """Test TaskLog ordering by timestamp."""
        # Create logs in specific order
        log1 = TaskLog.objects.create(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="First log")

        log2 = TaskLog.objects.create(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="Second log")

        log3 = TaskLog.objects.create(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="Third log")

        # Test default ordering (oldest first)
        logs = list(TaskLog.objects.filter(task_id=self.test_task_id))
        self.assertEqual(logs[0], log1)
        self.assertEqual(logs[1], log2)
        self.assertEqual(logs[2], log3)

    def test_task_log_filtering_by_task_id(self):
        """Test filtering TaskLog by task_id."""
        task_id_1 = str(uuid.uuid4())
        task_id_2 = str(uuid.uuid4())

        # Create logs for different tasks
        TaskLog.objects.create(task_id=task_id_1, level=logging.INFO, level_name="INFO", message="Task 1 log")

        TaskLog.objects.create(task_id=task_id_2, level=logging.INFO, level_name="INFO", message="Task 2 log")

        TaskLog.objects.create(task_id=task_id_1, level=logging.ERROR, level_name="ERROR", message="Task 1 error")

        # Test filtering
        task_1_logs = TaskLog.objects.filter(task_id=task_id_1)
        task_2_logs = TaskLog.objects.filter(task_id=task_id_2)

        self.assertEqual(task_1_logs.count(), 2)
        self.assertEqual(task_2_logs.count(), 1)

        # Test content
        task_1_messages = [log.message for log in task_1_logs]
        self.assertIn("Task 1 log", task_1_messages)
        self.assertIn("Task 1 error", task_1_messages)

        task_2_message = task_2_logs.first().message
        self.assertEqual(task_2_message, "Task 2 log")

    def test_task_log_filtering_by_level(self):
        """Test filtering TaskLog by log level."""
        # Create logs with different levels
        TaskLog.objects.create(task_id=self.test_task_id, level=logging.DEBUG, level_name="DEBUG", message="Debug message")

        TaskLog.objects.create(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="Info message")

        TaskLog.objects.create(task_id=self.test_task_id, level=logging.ERROR, level_name="ERROR", message="Error message")

        # Test level filtering - filter by task_id to avoid test pollution
        error_logs = TaskLog.objects.filter(task_id=self.test_task_id, level=logging.ERROR)
        info_logs = TaskLog.objects.filter(task_id=self.test_task_id, level=logging.INFO)
        debug_logs = TaskLog.objects.filter(task_id=self.test_task_id, level=logging.DEBUG)

        self.assertEqual(error_logs.count(), 1)
        self.assertEqual(info_logs.count(), 1)
        self.assertEqual(debug_logs.count(), 1)

        self.assertEqual(error_logs.first().message, "Error message")
        self.assertEqual(info_logs.first().message, "Info message")
        self.assertEqual(debug_logs.first().message, "Debug message")

    def test_task_log_with_extra_data(self):
        """Test TaskLog with extra_data JSON field."""
        extra_data = {"request_id": "abc123", "user_id": 456, "context": {"action": "test", "source": "unit_test"}}

        log = TaskLog.objects.create(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="Log with extra data", extra_data=extra_data)

        self.assertEqual(log.extra_data, extra_data)
        self.assertEqual(log.extra_data["request_id"], "abc123")
        self.assertEqual(log.extra_data["user_id"], 456)
        self.assertEqual(log.extra_data["context"]["action"], "test")

    def test_task_log_with_null_optional_fields(self):
        """Test TaskLog creation with null optional fields."""
        log = TaskLog.objects.create(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="Minimal log entry")

        # These fields should be null/blank
        self.assertEqual(log.module, "")
        self.assertEqual(log.function_name, "")
        self.assertIsNone(log.line_number)
        self.assertEqual(log.thread, "")  # CharField with blank=True, so empty string not None
        self.assertEqual(log.process, "")  # CharField with blank=True, so empty string not None
        self.assertIsNone(log.extra_data)

    def test_task_log_message_search(self):
        """Test searching TaskLog by message content."""
        # Create logs with different messages
        TaskLog.objects.create(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="Processing user data for analysis")

        TaskLog.objects.create(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="Database connection established")

        TaskLog.objects.create(task_id=self.test_task_id, level=logging.ERROR, level_name="ERROR", message="Failed to process user request")

        # Test message search
        user_logs = TaskLog.objects.filter(message__icontains="user")
        database_logs = TaskLog.objects.filter(message__icontains="database")
        process_logs = TaskLog.objects.filter(message__icontains="process")

        self.assertEqual(user_logs.count(), 2)
        self.assertEqual(database_logs.count(), 1)
        self.assertEqual(process_logs.count(), 2)

    def test_task_log_indexes(self):
        """Test that database indexes are working efficiently."""
        # Create multiple logs with unique task ID prefix to avoid test pollution
        unique_prefix = f"test_indexes_{self.test_task_id}"
        for i in range(10):
            TaskLog.objects.create(
                task_id=f"{unique_prefix}_{i % 3}",  # Create 3 different task IDs
                level=logging.INFO,
                level_name="INFO",
                message=f"Log message {i}",
            )

        # These queries should use indexes efficiently
        # (We can't directly test index usage in unit tests, but we ensure queries work)

        # Task ID index
        task_logs = TaskLog.objects.filter(task_id=f"{unique_prefix}_1")
        self.assertGreater(task_logs.count(), 0)

        # Timestamp index (used in ordering)
        recent_logs = TaskLog.objects.filter(task_id__startswith=unique_prefix).order_by("-timestamp")[:5]
        self.assertEqual(len(recent_logs), 5)

        # Level index - filter by our unique prefix
        info_logs = TaskLog.objects.filter(task_id__startswith=unique_prefix, level=logging.INFO)
        self.assertEqual(info_logs.count(), 10)

    def test_task_log_max_length_validation(self):
        """Test TaskLog field max length validation."""
        # Test task_id max length
        long_task_id = "x" * 256
        with self.assertRaises(ValidationError):
            log = TaskLog(task_id=long_task_id, level=logging.INFO, level_name="INFO", message="Test")
            log.full_clean()

        # Test module max length
        long_module = "x" * 256
        with self.assertRaises(ValidationError):
            log = TaskLog(task_id=self.test_task_id, level=logging.INFO, level_name="INFO", message="Test", module=long_module)
            log.full_clean()

    def test_task_log_bulk_operations(self):
        """Test bulk operations with TaskLog."""
        # Prepare bulk data
        bulk_logs = []
        for i in range(100):
            bulk_logs.append(TaskLog(task_id=f"{self.test_task_id}_bulk", level=logging.INFO, level_name="INFO", message=f"Bulk log {i}"))

        # Bulk create
        TaskLog.objects.bulk_create(bulk_logs)

        # Verify bulk creation
        created_logs = TaskLog.objects.filter(task_id=f"{self.test_task_id}_bulk")
        self.assertEqual(created_logs.count(), 100)

        # Test bulk filtering and aggregation
        from django.db.models import Count

        log_stats = TaskLog.objects.filter(task_id=f"{self.test_task_id}_bulk").aggregate(total_logs=Count("id"))

        self.assertEqual(log_stats["total_logs"], 100)

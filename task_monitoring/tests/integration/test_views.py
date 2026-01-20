"""Integration tests for task monitoring views."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from data_pipeline.models import Source, Variable
from task_monitoring.models import TaskExecution, TaskType


class TaskMonitoringViewTests(TestCase):
    """Tests for task monitoring views that actually exist."""

    def setUp(self):
        """Set up test data and authenticated client."""
        self.client = Client()

        # Create a staff user for views that require authentication
        self.staff_user = User.objects.create_user(
            username='teststaff',
            password='testpass',
            is_staff=True
        )

        self.task_type = TaskType.objects.create(name="test_task")

        # Create some test executions
        self.execution1 = TaskExecution.objects.create(
            task_id="exec-1",
            task_type=self.task_type,
            status="success",
            started_at=timezone.now() - timedelta(minutes=5),
            completed_at=timezone.now() - timedelta(minutes=4),
        )

        self.execution2 = TaskExecution.objects.create(
            task_id="exec-2",
            task_type=self.task_type,
            status="failure",
            error_message="Test error",
        )

    def test_task_executions_list_view(self):
        """Test task executions list view."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:task_executions_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "exec-1")
        self.assertContains(response, "exec-2")

    def test_task_executions_list_view_filtering(self):
        """Test task executions list view with filters."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:task_executions_list")

        # Filter by status
        response = self.client.get(url, {"status": "success"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "exec-1")
        self.assertNotContains(response, "exec-2")

    def test_task_executions_list_requires_login(self):
        """Test that task executions list requires login."""
        url = reverse("task_monitoring:task_executions_list")
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)


class ScheduledTaskViewTests(TestCase):
    """Tests for scheduled task management views."""

    def setUp(self):
        """Set up test data and authenticated client."""
        self.client = Client()

        # Create a staff user
        self.staff_user = User.objects.create_user(
            username='teststaff',
            password='testpass',
            is_staff=True
        )

        # Create test scheduled task
        self.interval = IntervalSchedule.objects.create(every=1, period="days")
        self.task = PeriodicTask.objects.create(
            name="Test Task",
            task="test.task",
            interval=self.interval,
            enabled=True,
        )

    def test_scheduled_tasks_list_view(self):
        """Test scheduled tasks list view."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:scheduled_tasks_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Task")
        self.assertContains(response, "Daily")  # Readable schedule format

    def test_scheduled_tasks_list_requires_staff(self):
        """Test that scheduled tasks list requires staff permission."""
        # Create non-staff user
        regular_user = User.objects.create_user(
            username='regular',
            password='testpass',
            is_staff=False
        )
        self.client.force_login(regular_user)

        url = reverse("task_monitoring:scheduled_tasks_list")
        response = self.client.get(url)

        # Should redirect (staff_member_required)
        self.assertEqual(response.status_code, 302)

    def test_scheduled_task_detail_view(self):
        """Test scheduled task detail view."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:scheduled_task_detail", args=[self.task.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Task")
        self.assertContains(response, "Daily")  # Readable schedule
        self.assertContains(response, "Next Execution")  # Next run info

    def test_scheduled_task_toggle(self):
        """Test toggling scheduled task status."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:toggle_scheduled_task", args=[self.task.id])

        # Task is initially enabled
        self.assertTrue(self.task.enabled)

        # Toggle to disabled
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect after POST

        # Check task was disabled
        self.task.refresh_from_db()
        self.assertFalse(self.task.enabled)

    def test_scheduled_task_delete(self):
        """Test deleting a scheduled task."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:delete_scheduled_task", args=[self.task.id])

        # Verify task exists
        self.assertTrue(PeriodicTask.objects.filter(id=self.task.id).exists())

        # Delete task
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect after POST

        # Verify task was deleted
        self.assertFalse(PeriodicTask.objects.filter(id=self.task.id).exists())

    @patch('celery.current_app.send_task')
    def test_scheduled_task_run_now(self, mock_send_task):
        """Test manually running a scheduled task."""
        # Mock the Celery task result
        mock_result = type('MockResult', (), {'id': 'mock-task-id'})()
        mock_send_task.return_value = mock_result

        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:run_scheduled_task", args=[self.task.id])

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect after POST

        # Verify Celery task was sent
        mock_send_task.assert_called_once_with(
            self.task.task,
            args=[],
            kwargs={}
        )

    def test_create_scheduled_task_get(self):
        """Test GET request to create scheduled task form."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:create_scheduled_task")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Scheduled Task")

    def test_create_scheduled_task_post(self):
        """Test POST request to create a new scheduled task."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:create_scheduled_task")

        data = {
            'name': 'New Test Task',
            'task': 'data_pipeline.tasks.full_pipeline',
            'description': 'Test description',
            'enabled': 'on',
            'schedule_type': 'interval',
            'every': '2',
            'period': 'hours',
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation

        # Verify task was created
        self.assertTrue(
            PeriodicTask.objects.filter(name='New Test Task').exists()
        )


class ScheduledTaskFormattingIntegrationTests(TestCase):
    """Integration tests for schedule formatting in views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.staff_user = User.objects.create_user(
            username='teststaff',
            password='testpass',
            is_staff=True
        )

    def test_interval_schedule_display(self):
        """Test that interval schedules display correctly in views."""
        # Create various interval schedules
        daily_interval = IntervalSchedule.objects.create(every=1, period="days")
        hourly_interval = IntervalSchedule.objects.create(every=1, period="hours")

        daily_task = PeriodicTask.objects.create(
            name="Daily Task",
            task="test.daily",
            interval=daily_interval,
            enabled=True,
        )

        hourly_task = PeriodicTask.objects.create(
            name="Hourly Task",
            task="test.hourly",
            interval=hourly_interval,
            enabled=True,
        )

        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:scheduled_tasks_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily")  # Should show "Daily" not "Every 1 days"
        self.assertContains(response, "Hourly")  # Should show "Hourly" not "Every 1 hours"

    def test_seconds_interval_display(self):
        """Test that second-based intervals display correctly."""
        # Create 86400 seconds interval (should display as "Daily")
        seconds_interval = IntervalSchedule.objects.create(every=86400, period="seconds")

        seconds_task = PeriodicTask.objects.create(
            name="Seconds Task",
            task="test.seconds",
            interval=seconds_interval,
            enabled=True,
        )

        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:scheduled_tasks_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should display as "Daily" not "Every 86400 seconds"
        self.assertContains(response, "Daily")
        self.assertNotContains(response, "86400")

    def test_next_run_time_display(self):
        """Test that next run times are displayed correctly."""
        interval = IntervalSchedule.objects.create(every=1, period="hours")
        task = PeriodicTask.objects.create(
            name="Next Run Test",
            task="test.nextrun",
            interval=interval,
            enabled=True,
            last_run_at=timezone.now() - timedelta(minutes=30)
        )

        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:scheduled_task_detail", args=[task.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Next Execution")
        # Should show time remaining
        self.assertContains(response, "In ")


class ViewErrorHandlingTests(TestCase):
    """Tests for error handling in views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.staff_user = User.objects.create_user(
            username='teststaff',
            password='testpass',
            is_staff=True
        )

    def test_scheduled_task_detail_not_found(self):
        """Test scheduled task detail view with non-existent task."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:scheduled_task_detail", args=[99999])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_toggle_task_not_found(self):
        """Test toggling non-existent task."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:toggle_scheduled_task", args=[99999])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)

    def test_delete_task_not_found(self):
        """Test deleting non-existent task."""
        self.client.force_login(self.staff_user)
        url = reverse("task_monitoring:delete_scheduled_task", args=[99999])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
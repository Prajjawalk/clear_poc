"""Integration tests for task monitoring API views."""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from data_pipeline.models import Source, Variable
from task_monitoring.models import TaskExecution, TaskType

User = get_user_model()


class TaskExecutionsAPITests(TestCase):
    """Tests for task executions API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create users
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            is_staff=False
        )

        # Create test data
        self.task_type = TaskType.objects.create(name="test_task")
        self.source = Source.objects.create(
            name="Test Source",
            type="api",
            class_name="TestSource"
        )
        self.variable = Variable.objects.create(
            source=self.source,
            name="Test Variable",
            code="test_var",
            period="day",
            adm_level=0,
            type="quantitative"
        )

        # Create test executions
        self.execution1 = TaskExecution.objects.create(
            task_id="exec-1",
            task_type=self.task_type,
            status="success",
            started_at=timezone.now() - timedelta(minutes=10),
            completed_at=timezone.now() - timedelta(minutes=5),
            source=self.source,
            variable=self.variable
        )

        self.execution2 = TaskExecution.objects.create(
            task_id="exec-2",
            task_type=self.task_type,
            status="failure",
            error_message="Test error",
            started_at=timezone.now() - timedelta(minutes=20),
            completed_at=timezone.now() - timedelta(minutes=15)
        )

    def test_api_requires_authentication(self):
        """Test that API requires authentication."""
        url = reverse('task_monitoring:executions_api')
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_executions_api_returns_list(self):
        """Test task executions API returns list of executions."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:executions_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertIn('pagination', data)
        self.assertEqual(len(data['data']), 2)

    def test_executions_api_filtering_by_status(self):
        """Test filtering executions by status."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:executions_api')
        response = self.client.get(url, {'status': 'success'})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['data'][0]['status'], 'success')

    def test_executions_api_filtering_by_task_type(self):
        """Test filtering executions by task type."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:executions_api')
        response = self.client.get(url, {'task_type': self.task_type.id})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 2)

    def test_executions_api_filtering_by_source(self):
        """Test filtering executions by source."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:executions_api')
        response = self.client.get(url, {'source': self.source.id})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['data'][0]['source']['id'], self.source.id)

    def test_executions_api_filtering_by_variable(self):
        """Test filtering executions by variable."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:executions_api')
        response = self.client.get(url, {'variable': self.variable.id})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['data'][0]['variable']['id'], self.variable.id)

    def test_executions_api_pagination(self):
        """Test API pagination."""
        self.client.login(username='testuser', password='testpass123')

        # Create more executions to test pagination
        for i in range(55):
            TaskExecution.objects.create(
                task_id=f"exec-page-{i}",
                task_type=self.task_type,
                status="pending"
            )

        url = reverse('task_monitoring:executions_api')
        response = self.client.get(url, {'page_size': 20})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 20)
        self.assertGreater(data['pagination']['total_pages'], 1)
        self.assertTrue(data['pagination']['has_next'])

    def test_executions_api_date_filtering(self):
        """Test filtering by date range."""
        self.client.login(username='testuser', password='testpass123')

        start_date = (timezone.now() - timedelta(hours=1)).isoformat()
        end_date = timezone.now().isoformat()

        url = reverse('task_monitoring:executions_api')
        response = self.client.get(url, {
            'start_date': start_date,
            'end_date': end_date
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_executions_api_error_handling(self):
        """Test API error handling."""
        self.client.login(username='testuser', password='testpass123')

        # Test with invalid parameters
        url = reverse('task_monitoring:executions_api')
        with patch('task_monitoring.views.TaskExecution.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            response = self.client.get(url)

            self.assertEqual(response.status_code, 500)
            data = response.json()
            self.assertFalse(data['success'])
            self.assertIn('error', data)


class TaskExecutionDetailAPITests(TestCase):
    """Tests for task execution detail API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        self.task_type = TaskType.objects.create(name="test_task")
        self.source = Source.objects.create(
            name="Test Source",
            type="api",
            class_name="TestSource"
        )

        self.execution = TaskExecution.objects.create(
            task_id="test-exec-1",
            task_type=self.task_type,
            status="success",
            started_at=timezone.now() - timedelta(minutes=10),
            completed_at=timezone.now() - timedelta(minutes=5),
            source=self.source,
            result={"processed": 100, "errors": 0}
        )

    def test_detail_api_requires_auth(self):
        """Test detail API requires authentication."""
        url = reverse('task_monitoring:execution_detail_api', args=[self.execution.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_detail_api_returns_execution(self):
        """Test detail API returns execution details."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:execution_detail_api', args=[self.execution.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertEqual(data['data']['id'], self.execution.id)
        self.assertEqual(data['data']['task_id'], 'test-exec-1')
        self.assertEqual(data['data']['status'], 'success')

    def test_detail_api_includes_relationships(self):
        """Test detail API includes related objects."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:execution_detail_api', args=[self.execution.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIsNotNone(data['data']['source'])
        self.assertEqual(data['data']['source']['id'], self.source.id)
        self.assertIsNotNone(data['data']['task_type'])
        self.assertEqual(data['data']['task_type']['id'], self.task_type.id)

    def test_detail_api_not_found(self):
        """Test detail API with non-existent execution."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:execution_detail_api', args=[99999])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data['success'])

    def test_detail_api_includes_computed_properties(self):
        """Test detail API includes computed properties."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:execution_detail_api', args=[self.execution.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn('duration_seconds', data['data'])
        self.assertIn('can_retry', data['data'])
        self.assertIn('is_completed', data['data'])


class TaskTypesAPITests(TestCase):
    """Tests for task types API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        self.task_type1 = TaskType.objects.create(name="retrieval")
        self.task_type2 = TaskType.objects.create(name="processing")

        # Create executions for statistics
        for i in range(5):
            TaskExecution.objects.create(
                task_id=f"exec-{i}",
                task_type=self.task_type1,
                status="success" if i < 3 else "failure"
            )

    def test_types_api_requires_auth(self):
        """Test types API requires authentication."""
        url = reverse('task_monitoring:types_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_types_api_returns_list(self):
        """Test types API returns list of task types."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:types_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 2)

    def test_types_api_includes_statistics(self):
        """Test types API includes execution statistics."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:types_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        retrieval_type = next(t for t in data['data'] if t['name'] == 'retrieval')
        self.assertEqual(retrieval_type['statistics']['total_executions'], 5)
        self.assertEqual(retrieval_type['statistics']['successful_executions'], 3)
        self.assertEqual(retrieval_type['statistics']['failed_executions'], 2)
        self.assertIsNotNone(retrieval_type['statistics']['success_rate'])


class TaskStatisticsAPITests(TestCase):
    """Tests for task statistics API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        self.task_type = TaskType.objects.create(name="test_task")

        # Create executions over different days
        now = timezone.now()
        for i in range(10):
            created_at = now - timedelta(days=i % 3)
            TaskExecution.objects.create(
                task_id=f"stat-exec-{i}",
                task_type=self.task_type,
                status="success" if i % 2 == 0 else "failure",
                created_at=created_at
            )

    def test_statistics_api_requires_auth(self):
        """Test statistics API requires authentication."""
        url = reverse('task_monitoring:statistics_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_statistics_api_returns_data(self):
        """Test statistics API returns statistical data."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:statistics_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertIn('period', data)
        self.assertIn('overall', data)
        self.assertIn('by_type', data)
        self.assertIn('by_day', data)

    def test_statistics_api_overall_stats(self):
        """Test overall statistics."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:statistics_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        overall = data['overall']
        self.assertGreater(overall['total_executions'], 0)
        self.assertIn('successful_executions', overall)
        self.assertIn('failed_executions', overall)
        self.assertIn('success_rate', overall)

    def test_statistics_api_by_type(self):
        """Test statistics broken down by task type."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:statistics_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        by_type = data['by_type']
        self.assertIn('test_task', by_type)

        type_stats = by_type['test_task']
        self.assertIn('total', type_stats)
        self.assertIn('successful', type_stats)
        self.assertIn('failed', type_stats)
        self.assertIn('success_rate', type_stats)

    def test_statistics_api_by_day(self):
        """Test daily statistics."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:statistics_api')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        by_day = data['by_day']
        self.assertGreater(len(by_day), 0)

        # Check structure of daily stats
        for date_key, day_stats in by_day.items():
            self.assertIn('total', day_stats)
            self.assertIn('successful', day_stats)
            self.assertIn('failed', day_stats)

    def test_statistics_api_date_range(self):
        """Test filtering statistics by date range."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:statistics_api')
        response = self.client.get(url, {'days': 3})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['period']['days'], 3)

    def test_statistics_api_error_handling(self):
        """Test statistics API error handling."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('task_monitoring:statistics_api')
        with patch('task_monitoring.views.TaskExecution.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            response = self.client.get(url)

            self.assertEqual(response.status_code, 500)
            data = response.json()
            self.assertFalse(data['success'])

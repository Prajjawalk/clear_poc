"""
Unit tests for data pipeline models.

Tests cover:
- Model field validation and constraints
- Relationships between models (Source, Variable, VariableData)
- Business logic methods and properties
- Database constraints and unique constraints
- Token management for SourceAuthToken
- TaskStatistics calculations and aggregations
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from data_pipeline.models import Source, Variable, VariableData, TaskStatistics, SourceAuthToken
from location.models import AdmLevel, Location


class SourceModelTest(TestCase):
    """Test Source model functionality."""

    def setUp(self):
        """Create test data."""
        self.source_data = {
            'name': 'Test ACLED Source',
            'description': 'Test data source for conflict events',
            'type': 'api',
            'base_url': 'https://api.acleddata.com',
            'class_name': 'ACLED',
            'is_active': True
        }

    def test_source_creation(self):
        """Test creating a source with valid data."""
        source = Source.objects.create(**self.source_data)
        
        self.assertEqual(source.name, 'Test ACLED Source')
        self.assertEqual(source.type, 'api')
        self.assertTrue(source.is_active)
        self.assertIsNotNone(source.created_at)
        self.assertIsNotNone(source.updated_at)

    def test_source_string_representation(self):
        """Test source string representation."""
        source = Source.objects.create(**self.source_data)
        self.assertEqual(str(source), 'Test ACLED Source')

    def test_source_type_choices_validation(self):
        """Test that source type is validated against choices."""
        invalid_data = self.source_data.copy()
        invalid_data['type'] = 'invalid_type'
        
        source = Source(**invalid_data)
        with self.assertRaises(ValidationError):
            source.full_clean()

    def test_source_ordering(self):
        """Test that sources are ordered by name."""
        Source.objects.create(name='Zebra Source', **{k: v for k, v in self.source_data.items() if k != 'name'})
        Source.objects.create(name='Alpha Source', **{k: v for k, v in self.source_data.items() if k != 'name'})
        
        sources = list(Source.objects.all())
        self.assertEqual(sources[0].name, 'Alpha Source')
        self.assertEqual(sources[1].name, 'Zebra Source')

    def test_source_url_validation(self):
        """Test URL field validation."""
        invalid_data = self.source_data.copy()
        invalid_data['base_url'] = 'not-a-valid-url'
        
        source = Source(**invalid_data)
        with self.assertRaises(ValidationError):
            source.full_clean()

    def test_source_optional_fields(self):
        """Test that optional fields can be empty."""
        minimal_data = {
            'name': 'Minimal Source',
            'type': 'api',
            'class_name': 'MinimalSource'
        }
        
        source = Source.objects.create(**minimal_data)
        self.assertEqual(source.description, '')
        self.assertEqual(source.info_url, '')
        self.assertEqual(source.base_url, '')
        self.assertEqual(source.comment, '')


class VariableModelTest(TestCase):
    """Test Variable model functionality."""

    def setUp(self):
        """Create test data."""
        self.source = Source.objects.create(
            name='Test Source',
            type='api',
            class_name='TestSource'
        )

        self.variable_data = {
            'source': self.source,
            'name': 'Test Conflict Events',
            'code': 'test_conflict_events',
            'period': 'day',
            'adm_level': 1,
            'type': 'quantitative',
            'unit': 'events',
            'text': 'Daily conflict events data'
        }

    def test_variable_creation(self):
        """Test creating a variable with valid data."""
        variable = Variable.objects.create(**self.variable_data)
        
        self.assertEqual(variable.name, 'Test Conflict Events')
        self.assertEqual(variable.code, 'test_conflict_events')
        self.assertEqual(variable.period, 'day')
        self.assertEqual(variable.adm_level, 1)
        self.assertEqual(variable.source, self.source)

    def test_variable_string_representation(self):
        """Test variable string representation."""
        variable = Variable.objects.create(**self.variable_data)
        expected_str = f"{self.source.name} - {variable.name}"
        self.assertEqual(str(variable), expected_str)

    def test_variable_unique_constraint(self):
        """Test unique constraint on source + code."""
        Variable.objects.create(**self.variable_data)
        
        # Try to create another variable with same source and code
        duplicate_data = self.variable_data.copy()
        duplicate_data['name'] = 'Different Name'
        
        with self.assertRaises(IntegrityError):
            Variable.objects.create(**duplicate_data)

    def test_variable_period_choices_validation(self):
        """Test that period is validated against choices."""
        invalid_data = self.variable_data.copy()
        invalid_data['period'] = 'invalid_period'
        
        variable = Variable(**invalid_data)
        with self.assertRaises(ValidationError):
            variable.full_clean()

    def test_variable_type_choices_validation(self):
        """Test that type is validated against choices."""
        invalid_data = self.variable_data.copy()
        invalid_data['type'] = 'invalid_type'
        
        variable = Variable(**invalid_data)
        with self.assertRaises(ValidationError):
            variable.full_clean()

    def test_variable_adm_level_validation(self):
        """Test that admin level must be non-negative."""
        invalid_data = self.variable_data.copy()
        invalid_data['adm_level'] = -1
        
        variable = Variable(**invalid_data)
        with self.assertRaises(ValidationError):
            variable.full_clean()

    def test_variable_cascade_delete(self):
        """Test that variables are deleted when source is deleted."""
        variable = Variable.objects.create(**self.variable_data)
        variable_id = variable.id
        
        self.source.delete()
        
        with self.assertRaises(Variable.DoesNotExist):
            Variable.objects.get(id=variable_id)


class VariableDataModelTest(TestCase):
    """Test VariableData model functionality."""

    def setUp(self):
        """Create test data."""
        self.source = Source.objects.create(
            name='Test Source',
            type='api', 
            class_name='TestSource'
        )

        self.variable = Variable.objects.create(
            source=self.source,
            name='Test Variable',
            code='test_var',
            period='day',
            adm_level=1,
            type='quantitative'
        )

        # Create admin level and location
        self.admin_level = AdmLevel.objects.create(
            code='1',
            name='Admin Level 1'
        )

        self.location = Location.objects.create(
            geo_id='TEST001',
            name='Test Location',
            admin_level=self.admin_level
        )

        self.data_record_data = {
            'variable': self.variable,
            'start_date': date(2024, 1, 1),
            'end_date': date(2024, 1, 1),
            'period': 'day',
            'adm_level': self.admin_level,
            'gid': self.location,
            'value': 100.0,
            'text': 'Test data record'
        }

    def test_variable_data_creation(self):
        """Test creating variable data with valid data."""
        data_record = VariableData.objects.create(**self.data_record_data)
        
        self.assertEqual(data_record.variable, self.variable)
        self.assertEqual(data_record.start_date, date(2024, 1, 1))
        self.assertEqual(data_record.value, 100.0)
        self.assertEqual(data_record.gid, self.location)
        self.assertIsNotNone(data_record.created_at)

    def test_variable_data_string_representation(self):
        """Test variable data string representation."""
        data_record = VariableData.objects.create(**self.data_record_data)
        expected_str = f"{self.variable.code} - {self.location.geo_id} ({data_record.start_date} to {data_record.end_date})"
        self.assertEqual(str(data_record), expected_str)

    def test_variable_data_unique_constraint(self):
        """Test unique constraint on variable + dates + location."""
        VariableData.objects.create(**self.data_record_data)
        
        # Try to create duplicate record
        duplicate_data = self.data_record_data.copy()
        duplicate_data['value'] = 200.0  # Different value
        
        with self.assertRaises(IntegrityError):
            VariableData.objects.create(**duplicate_data)

    def test_variable_data_without_location(self):
        """Test creating variable data without matched location."""
        data_without_location = self.data_record_data.copy()
        data_without_location['gid'] = None
        data_without_location['original_location_text'] = 'Unmatched Location Name'
        
        data_record = VariableData.objects.create(**data_without_location)
        self.assertIsNone(data_record.gid)
        self.assertEqual(data_record.original_location_text, 'Unmatched Location Name')

    def test_variable_data_parent_relationship(self):
        """Test parent-child relationships for derived data."""
        # Create original data record
        original_data = VariableData.objects.create(**self.data_record_data)
        
        # Create derived data record
        derived_data_params = self.data_record_data.copy()
        derived_data_params['start_date'] = date(2024, 1, 2)
        derived_data_params['end_date'] = date(2024, 1, 2)
        derived_data_params['parent'] = original_data
        derived_data_params['value'] = 150.0
        
        derived_data = VariableData.objects.create(**derived_data_params)
        
        # Test properties
        self.assertTrue(original_data.is_original)
        self.assertFalse(original_data.is_derived)
        self.assertFalse(derived_data.is_original)
        self.assertTrue(derived_data.is_derived)
        
        # Test relationships
        self.assertEqual(derived_data.parent, original_data)
        self.assertIn(derived_data, original_data.derived_records.all())

    def test_variable_data_lineage_tracking(self):
        """Test lineage tracking for multi-level derived data."""
        # Create original data
        original_data = VariableData.objects.create(**self.data_record_data)
        
        # Create first-level derived data
        level1_params = self.data_record_data.copy()
        level1_params['start_date'] = date(2024, 1, 2)
        level1_params['end_date'] = date(2024, 1, 2)
        level1_params['parent'] = original_data
        level1_params['value'] = 120.0
        level1_data = VariableData.objects.create(**level1_params)
        
        # Create second-level derived data
        level2_params = self.data_record_data.copy()
        level2_params['start_date'] = date(2024, 1, 3)
        level2_params['end_date'] = date(2024, 1, 3)
        level2_params['parent'] = level1_data
        level2_params['value'] = 140.0
        level2_data = VariableData.objects.create(**level2_params)
        
        # Test lineage
        lineage = level2_data.get_lineage()
        self.assertEqual(len(lineage), 3)
        self.assertEqual(lineage[0], original_data)  # Root parent first
        self.assertEqual(lineage[1], level1_data)
        self.assertEqual(lineage[2], level2_data)   # Self last
        
        # Test root parent
        self.assertEqual(level2_data.get_root_parent(), original_data)
        self.assertEqual(level1_data.get_root_parent(), original_data)
        self.assertEqual(original_data.get_root_parent(), original_data)

    def test_variable_data_period_choices_validation(self):
        """Test that period is validated against choices."""
        invalid_data = self.data_record_data.copy()
        invalid_data['period'] = 'invalid_period'
        
        data_record = VariableData(**invalid_data)
        with self.assertRaises(ValidationError):
            data_record.full_clean()

    def test_variable_data_cascade_protection(self):
        """Test that foreign key deletions are protected."""
        data_record = VariableData.objects.create(**self.data_record_data)
        
        # Location deletion should be protected
        with self.assertRaises(IntegrityError):
            self.location.delete()
            
        # Admin level deletion should be protected
        with self.assertRaises(IntegrityError):
            self.admin_level.delete()


class TaskStatisticsModelTest(TestCase):
    """Test TaskStatistics model functionality."""

    def setUp(self):
        """Create test data."""
        self.stats_data = {
            'date': date(2024, 1, 1),
            'check_updates_count': 5,
            'download_data_count': 3,
            'process_data_count': 2,
            'full_pipeline_count': 1,
            'reprocess_data_count': 0,
            'success_count': 8,
            'failure_count': 3,
            'retry_count': 2,
            'avg_duration_seconds': 45.5,
            'max_duration_seconds': 120.0
        }

    def test_task_statistics_creation(self):
        """Test creating task statistics with valid data."""
        stats = TaskStatistics.objects.create(**self.stats_data)
        
        self.assertEqual(stats.date, date(2024, 1, 1))
        self.assertEqual(stats.success_count, 8)
        self.assertEqual(stats.failure_count, 3)
        self.assertEqual(stats.avg_duration_seconds, 45.5)

    def test_task_statistics_string_representation(self):
        """Test task statistics string representation."""
        stats = TaskStatistics.objects.create(**self.stats_data)
        expected_str = f"Task Stats - {stats.date}"
        self.assertEqual(str(stats), expected_str)

    def test_task_statistics_unique_date_constraint(self):
        """Test unique constraint on date."""
        TaskStatistics.objects.create(**self.stats_data)
        
        # Try to create another stats record for same date
        duplicate_data = self.stats_data.copy()
        duplicate_data['success_count'] = 10
        
        with self.assertRaises(IntegrityError):
            TaskStatistics.objects.create(**duplicate_data)

    def test_task_statistics_total_tasks_property(self):
        """Test total_tasks property calculation."""
        stats = TaskStatistics.objects.create(**self.stats_data)
        
        expected_total = (
            stats.check_updates_count + stats.download_data_count + 
            stats.process_data_count + stats.full_pipeline_count + 
            stats.reprocess_data_count
        )
        
        self.assertEqual(stats.total_tasks, expected_total)
        self.assertEqual(stats.total_tasks, 11)  # 5+3+2+1+0

    def test_task_statistics_success_rate_property(self):
        """Test success_rate property calculation."""
        stats = TaskStatistics.objects.create(**self.stats_data)
        
        expected_rate = (stats.success_count / (stats.success_count + stats.failure_count)) * 100
        self.assertEqual(stats.success_rate, expected_rate)
        self.assertAlmostEqual(stats.success_rate, 72.73, places=2)  # 8/(8+3) * 100

    def test_task_statistics_success_rate_no_tasks(self):
        """Test success rate when there are no tasks."""
        stats_data = self.stats_data.copy()
        stats_data['success_count'] = 0
        stats_data['failure_count'] = 0
        
        stats = TaskStatistics.objects.create(**stats_data)
        self.assertIsNone(stats.success_rate)

    def test_task_statistics_default_values(self):
        """Test that count fields have proper defaults."""
        minimal_stats = TaskStatistics.objects.create(date=date(2024, 1, 2))
        
        self.assertEqual(minimal_stats.check_updates_count, 0)
        self.assertEqual(minimal_stats.download_data_count, 0)
        self.assertEqual(minimal_stats.success_count, 0)
        self.assertEqual(minimal_stats.failure_count, 0)
        self.assertIsNone(minimal_stats.avg_duration_seconds)

    def test_task_statistics_ordering(self):
        """Test that statistics are ordered by date descending."""
        TaskStatistics.objects.create(date=date(2024, 1, 1), success_count=5)
        TaskStatistics.objects.create(date=date(2024, 1, 3), success_count=8)
        TaskStatistics.objects.create(date=date(2024, 1, 2), success_count=6)
        
        stats_list = list(TaskStatistics.objects.all())
        self.assertEqual(stats_list[0].date, date(2024, 1, 3))  # Most recent first
        self.assertEqual(stats_list[1].date, date(2024, 1, 2))
        self.assertEqual(stats_list[2].date, date(2024, 1, 1))  # Oldest last


class SourceAuthTokenModelTest(TestCase):
    """Test SourceAuthToken model functionality."""

    def setUp(self):
        """Create test data."""
        self.source = Source.objects.create(
            name='Test OAuth Source',
            type='api',
            class_name='OAuthSource'
        )

        self.token_data = {
            'source': self.source,
            'access_token': 'test_access_token_123',
            'refresh_token': 'test_refresh_token_456',
            'token_type': 'Bearer',
            'expires_at': timezone.now() + timedelta(hours=1),
            'refresh_expires_at': timezone.now() + timedelta(days=30),
            'metadata': {'scope': 'read:data', 'user_id': '12345'}
        }

    def test_source_auth_token_creation(self):
        """Test creating auth token with valid data."""
        token = SourceAuthToken.objects.create(**self.token_data)
        
        self.assertEqual(token.source, self.source)
        self.assertEqual(token.access_token, 'test_access_token_123')
        self.assertEqual(token.token_type, 'Bearer')
        self.assertIsNotNone(token.expires_at)
        self.assertEqual(token.metadata['scope'], 'read:data')

    def test_source_auth_token_string_representation(self):
        """Test auth token string representation."""
        token = SourceAuthToken.objects.create(**self.token_data)
        expected_str = f"Auth Token - {self.source.name}"
        self.assertEqual(str(token), expected_str)

    def test_source_auth_token_one_to_one_constraint(self):
        """Test one-to-one relationship constraint."""
        SourceAuthToken.objects.create(**self.token_data)
        
        # Try to create another token for same source
        duplicate_data = self.token_data.copy()
        duplicate_data['access_token'] = 'different_token'
        
        with self.assertRaises(IntegrityError):
            SourceAuthToken.objects.create(**duplicate_data)

    def test_access_token_validity(self):
        """Test access token validity checking."""
        # Valid token (expires in 1 hour)
        token = SourceAuthToken.objects.create(**self.token_data)
        self.assertTrue(token.is_access_token_valid())
        
        # Expired token
        expired_data = self.token_data.copy()
        expired_data['expires_at'] = timezone.now() - timedelta(hours=1)
        expired_data['source'] = Source.objects.create(name='Expired Source', type='api', class_name='ExpiredSource')
        expired_token = SourceAuthToken.objects.create(**expired_data)
        self.assertFalse(expired_token.is_access_token_valid())
        
        # No expiration set (should be valid)
        no_expiry_data = self.token_data.copy()
        no_expiry_data['expires_at'] = None
        no_expiry_data['source'] = Source.objects.create(name='No Expiry Source', type='api', class_name='NoExpirySource')
        no_expiry_token = SourceAuthToken.objects.create(**no_expiry_data)
        self.assertTrue(no_expiry_token.is_access_token_valid())
        
        # No access token
        no_token_data = self.token_data.copy()
        no_token_data['access_token'] = ''
        no_token_data['source'] = Source.objects.create(name='No Token Source', type='api', class_name='NoTokenSource')
        no_token = SourceAuthToken.objects.create(**no_token_data)
        self.assertFalse(no_token.is_access_token_valid())

    def test_refresh_token_validity(self):
        """Test refresh token validity checking."""
        token = SourceAuthToken.objects.create(**self.token_data)
        self.assertTrue(token.is_refresh_token_valid())
        
        # Expired refresh token
        expired_refresh_data = self.token_data.copy()
        expired_refresh_data['refresh_expires_at'] = timezone.now() - timedelta(days=1)
        expired_refresh_data['source'] = Source.objects.create(name='Expired Refresh Source', type='api', class_name='ExpiredRefreshSource')
        expired_refresh_token = SourceAuthToken.objects.create(**expired_refresh_data)
        self.assertFalse(expired_refresh_token.is_refresh_token_valid())

    def test_token_needs_refresh(self):
        """Test token refresh necessity checking."""
        # Token expires in 10 minutes (should need refresh with 5 min buffer)
        soon_expire_data = self.token_data.copy()
        soon_expire_data['expires_at'] = timezone.now() + timedelta(minutes=3)
        soon_expire_data['source'] = Source.objects.create(name='Soon Expire Source', type='api', class_name='SoonExpireSource')
        soon_expire_token = SourceAuthToken.objects.create(**soon_expire_data)
        self.assertTrue(soon_expire_token.needs_refresh(buffer_minutes=5))
        
        # Token expires in 1 hour (should not need refresh)
        token = SourceAuthToken.objects.create(**self.token_data)
        self.assertFalse(token.needs_refresh(buffer_minutes=5))
        
        # No expiration (should not need refresh)
        no_expiry_data = self.token_data.copy()
        no_expiry_data['expires_at'] = None
        no_expiry_data['source'] = Source.objects.create(name='No Expiry Source2', type='api', class_name='NoExpirySource2')
        no_expiry_token = SourceAuthToken.objects.create(**no_expiry_data)
        self.assertFalse(no_expiry_token.needs_refresh())

    def test_clear_tokens(self):
        """Test clearing stored tokens."""
        token = SourceAuthToken.objects.create(**self.token_data)
        
        # Verify tokens are set
        self.assertNotEqual(token.access_token, '')
        self.assertNotEqual(token.refresh_token, '')
        self.assertIsNotNone(token.expires_at)
        self.assertNotEqual(token.metadata, {})
        
        # Clear tokens
        token.clear_tokens()
        
        # Verify tokens are cleared
        self.assertEqual(token.access_token, '')
        self.assertEqual(token.refresh_token, '')
        self.assertIsNone(token.expires_at)
        self.assertIsNone(token.refresh_expires_at)
        self.assertEqual(token.metadata, {})

    def test_default_metadata(self):
        """Test that metadata defaults to empty dict."""
        minimal_token_data = {
            'source': self.source,
            'access_token': 'test_token'
        }
        
        token = SourceAuthToken.objects.create(**minimal_token_data)
        self.assertEqual(token.metadata, {})
        self.assertEqual(token.token_type, 'Bearer')  # Default value

    def test_cascade_delete_with_source(self):
        """Test that auth token is deleted when source is deleted."""
        token = SourceAuthToken.objects.create(**self.token_data)
        token_id = token.id
        
        self.source.delete()
        
        with self.assertRaises(SourceAuthToken.DoesNotExist):
            SourceAuthToken.objects.get(id=token_id)
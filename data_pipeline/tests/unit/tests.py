"""Comprehensive tests for the data_pipeline app."""

from datetime import date, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from location.models import AdmLevel, Location

from data_pipeline.models import Source, TaskStatistics, Variable, VariableData


class SourceModelTests(TestCase):
    """Tests for Source model."""

    def setUp(self):
        """Set up test data."""
        self.source = Source.objects.create(
            name="Test Source",
            description="A test data source",
            type="api",
            info_url="https://example.com/info",
            base_url="https://api.example.com",
            class_name="TestAPISource",
            comment="Test comment"
        )

    def test_source_creation(self):
        """Test Source model creation."""
        self.assertEqual(self.source.name, "Test Source")
        self.assertEqual(self.source.type, "api")
        self.assertEqual(self.source.class_name, "TestAPISource")
        self.assertTrue(self.source.created_at)
        self.assertTrue(self.source.updated_at)
        self.assertEqual(str(self.source), "Test Source")

    def test_source_type_choices(self):
        """Test all valid source type choices."""
        valid_types = ["api", "web_scraping", "file_upload", "ftp", "database"]

        for source_type in valid_types:
            source = Source.objects.create(
                name=f"Test {source_type}",
                type=source_type,
                class_name="TestClass"
            )
            self.assertEqual(source.type, source_type)

    def test_source_ordering(self):
        """Test Source ordering by name."""
        Source.objects.create(name="Zebra Source", type="api", class_name="ZebraSource")
        Source.objects.create(name="Alpha Source", type="api", class_name="AlphaSource")

        sources = list(Source.objects.all())
        names = [source.name for source in sources]

        self.assertEqual(names, ["Alpha Source", "Test Source", "Zebra Source"])

    def test_source_optional_fields(self):
        """Test Source with minimal required fields."""
        minimal_source = Source.objects.create(
            name="Minimal Source",
            type="file_upload",
            class_name="MinimalSource"
        )

        self.assertEqual(minimal_source.description, "")
        self.assertEqual(minimal_source.info_url, "")
        self.assertEqual(minimal_source.base_url, "")
        self.assertEqual(minimal_source.comment, "")

    def test_source_url_validation(self):
        """Test URL field validation."""
        # Valid URLs should work
        valid_source = Source(
            name="Valid URL Source",
            type="api",
            class_name="ValidSource",
            info_url="https://example.com",
            base_url="https://api.example.com/v1"
        )
        valid_source.full_clean()  # Should not raise

        # Invalid URLs should raise validation error
        with self.assertRaises(ValidationError):
            invalid_source = Source(
                name="Invalid URL Source",
                type="api",
                class_name="InvalidSource",
                info_url="not-a-url"
            )
            invalid_source.full_clean()


class VariableModelTests(TestCase):
    """Tests for Variable model."""

    def setUp(self):
        """Set up test data."""
        self.source = Source.objects.create(
            name="ACLED",
            type="api",
            class_name="ACLEDSource"
        )

        self.variable = Variable.objects.create(
            source=self.source,
            name="Fatalities",
            code="fatalities",
            period="day",
            adm_level=1,
            type="quantitative",
            text="Number of conflict-related fatalities"
        )

    def test_variable_creation(self):
        """Test Variable model creation."""
        self.assertEqual(self.variable.name, "Fatalities")
        self.assertEqual(self.variable.code, "fatalities")
        self.assertEqual(self.variable.source, self.source)
        self.assertEqual(self.variable.period, "day")
        self.assertEqual(self.variable.adm_level, 1)
        self.assertEqual(self.variable.type, "quantitative")
        self.assertTrue(self.variable.created_at)
        self.assertTrue(self.variable.updated_at)

    def test_variable_str_representation(self):
        """Test Variable string representation."""
        expected = "ACLED - Fatalities"
        self.assertEqual(str(self.variable), expected)

    def test_variable_period_choices(self):
        """Test all valid period choices."""
        valid_periods = ["day", "week", "month", "quarter", "year", "event"]

        for period in valid_periods:
            variable = Variable.objects.create(
                source=self.source,
                name=f"Test {period}",
                code=f"test_{period}",
                period=period,
                adm_level=0,
                type="quantitative"
            )
            self.assertEqual(variable.period, period)

    def test_variable_type_choices(self):
        """Test all valid type choices."""
        valid_types = ["quantitative", "qualitative", "textual", "categorical"]

        for var_type in valid_types:
            variable = Variable.objects.create(
                source=self.source,
                name=f"Test {var_type}",
                code=f"test_{var_type}",
                period="day",
                adm_level=0,
                type=var_type
            )
            self.assertEqual(variable.type, var_type)

    def test_variable_adm_level_validation(self):
        """Test administrative level validation."""
        # Valid admin levels (0 and positive integers)
        for level in [0, 1, 2, 3]:
            variable = Variable(
                source=self.source,
                name=f"Test Level {level}",
                code=f"test_level_{level}",
                period="day",
                adm_level=level,
                type="quantitative"
            )
            variable.full_clean()  # Should not raise

        # Negative admin level should raise validation error
        with self.assertRaises(ValidationError):
            invalid_variable = Variable(
                source=self.source,
                name="Invalid Level",
                code="invalid_level",
                period="day",
                adm_level=-1,
                type="quantitative"
            )
            invalid_variable.full_clean()

    def test_variable_unique_together_constraint(self):
        """Test unique_together constraint on source and code."""
        # Creating another variable with same source and code should fail
        with self.assertRaises(Exception):
            Variable.objects.create(
                source=self.source,
                name="Duplicate Code",
                code="fatalities",  # Same code as existing variable
                period="week",
                adm_level=2,
                type="qualitative"
            )

    def test_variable_ordering(self):
        """Test Variable ordering by source name and variable name."""
        # Create another source
        source2 = Source.objects.create(
            name="Beta Source",
            type="api",
            class_name="BetaSource"
        )

        Variable.objects.create(
            source=source2,
            name="Alpha Variable",
            code="alpha_var",
            period="day",
            adm_level=0,
            type="quantitative"
        )

        Variable.objects.create(
            source=self.source,
            name="Beta Variable",
            code="beta_var",
            period="day",
            adm_level=0,
            type="quantitative"
        )

        variables = list(Variable.objects.all())
        # Should be ordered by source name, then variable name
        expected_order = [
            "ACLED - Beta Variable",
            "ACLED - Fatalities",
            "Beta Source - Alpha Variable"
        ]
        actual_order = [str(var) for var in variables]
        self.assertEqual(actual_order, expected_order)

    def test_variable_cascade_delete(self):
        """Test cascade delete when source is deleted."""
        variable_id = self.variable.id
        self.source.delete()

        # Variable should be deleted due to CASCADE
        with self.assertRaises(Variable.DoesNotExist):
            Variable.objects.get(id=variable_id)


class VariableDataModelTests(TestCase):
    """Tests for VariableData model."""

    def setUp(self):
        """Set up test data."""
        # Create location data
        self.admin_level = AdmLevel.objects.create(code="1", name="Admin1")
        self.location = Location.objects.create(
            geo_id="SD_001",
            name="Khartoum",
            admin_level=self.admin_level
        )

        # Create source and variable
        self.source = Source.objects.create(
            name="ACLED",
            type="api",
            class_name="ACLEDSource"
        )

        self.variable = Variable.objects.create(
            source=self.source,
            name="Fatalities",
            code="fatalities",
            period="day",
            adm_level=1,
            type="quantitative"
        )

        # Create variable data
        self.var_data = VariableData.objects.create(
            variable=self.variable,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            period="day",
            adm_level=self.admin_level,
            gid=self.location,
            value=25.5,
            text="25 fatalities reported"
        )

    def test_variable_data_creation(self):
        """Test VariableData model creation."""
        self.assertEqual(self.var_data.variable, self.variable)
        self.assertEqual(self.var_data.start_date, date(2024, 1, 1))
        self.assertEqual(self.var_data.end_date, date(2024, 1, 1))
        self.assertEqual(self.var_data.adm_level, self.admin_level)
        self.assertEqual(self.var_data.gid, self.location)
        self.assertEqual(self.var_data.value, 25.5)
        self.assertEqual(self.var_data.text, "25 fatalities reported")
        self.assertTrue(self.var_data.created_at)
        self.assertTrue(self.var_data.updated_at)

    def test_variable_data_str_representation(self):
        """Test VariableData string representation."""
        expected = "fatalities - SD_001 (2024-01-01 to 2024-01-01)"
        self.assertEqual(str(self.var_data), expected)

    def test_variable_data_ordering(self):
        """Test VariableData ordering by end_date desc and geo_id."""
        # Create additional data records
        location2 = Location.objects.create(
            geo_id="SD_002",
            name="Kassala",
            admin_level=self.admin_level
        )

        # Earlier date, different location
        VariableData.objects.create(
            variable=self.variable,
            start_date=date(2023, 12, 31),
            end_date=date(2023, 12, 31),
            period="day",
            adm_level=self.admin_level,
            gid=location2,
            value=10.0
        )

        # Same date, different location (should come first alphabetically)
        VariableData.objects.create(
            variable=self.variable,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            period="day",
            adm_level=self.admin_level,
            gid=location2,
            value=15.0
        )

        data_records = list(VariableData.objects.all())

        # Should be ordered by end_date desc, then geo_id
        self.assertEqual(data_records[0].end_date, date(2024, 1, 1))
        self.assertEqual(data_records[0].gid.geo_id, "SD_001")  # Original record

        self.assertEqual(data_records[1].end_date, date(2024, 1, 1))
        self.assertEqual(data_records[1].gid.geo_id, "SD_002")  # Same date, different location

        self.assertEqual(data_records[2].end_date, date(2023, 12, 31))
        self.assertEqual(data_records[2].gid.geo_id, "SD_002")  # Earlier date

    def test_variable_data_unique_together_constraint(self):
        """Test unique_together constraint."""
        # Creating another record with same variable, dates, and location should fail
        with self.assertRaises(Exception):
            VariableData.objects.create(
                variable=self.variable,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
                period="day",
                adm_level=self.admin_level,
                gid=self.location,
                value=30.0
            )

    def test_variable_data_optional_fields(self):
        """Test VariableData with optional fields."""
        # Create record with only required fields
        minimal_data = VariableData.objects.create(
            variable=self.variable,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 1),
            period="day",
            adm_level=self.admin_level,
            gid=self.location
        )

        self.assertIsNone(minimal_data.value)
        self.assertEqual(minimal_data.text, "")

    def test_variable_data_cascade_relationships(self):
        """Test cascade behavior for VariableData relationships."""
        data_id = self.var_data.id

        # Deleting variable should delete data (CASCADE)
        self.variable.delete()

        with self.assertRaises(VariableData.DoesNotExist):
            VariableData.objects.get(id=data_id)

    def test_variable_data_protect_relationships(self):
        """Test PROTECT behavior for location relationships."""
        # Should not be able to delete location due to PROTECT
        with self.assertRaises(Exception):
            self.location.delete()


class TaskStatisticsModelTests(TestCase):
    """Tests for TaskStatistics model."""

    def setUp(self):
        """Set up test data."""
        self.stats = TaskStatistics.objects.create(
            date=date(2024, 1, 15),
            check_updates_count=10,
            download_data_count=5,
            process_data_count=8,
            full_pipeline_count=2,
            reprocess_data_count=1,
            success_count=20,
            failure_count=6,
            retry_count=3,
            avg_duration_seconds=45.5,
            max_duration_seconds=120.0
        )

    def test_task_statistics_creation(self):
        """Test TaskStatistics model creation."""
        self.assertEqual(self.stats.date, date(2024, 1, 15))
        self.assertEqual(self.stats.check_updates_count, 10)
        self.assertEqual(self.stats.download_data_count, 5)
        self.assertEqual(self.stats.process_data_count, 8)
        self.assertEqual(self.stats.full_pipeline_count, 2)
        self.assertEqual(self.stats.reprocess_data_count, 1)
        self.assertEqual(self.stats.success_count, 20)
        self.assertEqual(self.stats.failure_count, 6)
        self.assertEqual(self.stats.retry_count, 3)
        self.assertEqual(self.stats.avg_duration_seconds, 45.5)
        self.assertEqual(self.stats.max_duration_seconds, 120.0)
        self.assertTrue(self.stats.created_at)
        self.assertTrue(self.stats.updated_at)

    def test_task_statistics_str_representation(self):
        """Test TaskStatistics string representation."""
        expected = "Task Stats - 2024-01-15"
        self.assertEqual(str(self.stats), expected)

    def test_task_statistics_default_values(self):
        """Test TaskStatistics default field values."""
        minimal_stats = TaskStatistics.objects.create(
            date=date(2024, 1, 16)
        )

        self.assertEqual(minimal_stats.check_updates_count, 0)
        self.assertEqual(minimal_stats.download_data_count, 0)
        self.assertEqual(minimal_stats.process_data_count, 0)
        self.assertEqual(minimal_stats.full_pipeline_count, 0)
        self.assertEqual(minimal_stats.reprocess_data_count, 0)
        self.assertEqual(minimal_stats.success_count, 0)
        self.assertEqual(minimal_stats.failure_count, 0)
        self.assertEqual(minimal_stats.retry_count, 0)
        self.assertIsNone(minimal_stats.avg_duration_seconds)
        self.assertIsNone(minimal_stats.max_duration_seconds)

    def test_task_statistics_unique_date(self):
        """Test that TaskStatistics dates must be unique."""
        with self.assertRaises(Exception):
            TaskStatistics.objects.create(
                date=date(2024, 1, 15)  # Same date as existing record
            )

    def test_task_statistics_ordering(self):
        """Test TaskStatistics ordering by date descending."""
        TaskStatistics.objects.create(date=date(2024, 1, 10))
        TaskStatistics.objects.create(date=date(2024, 1, 20))

        stats = list(TaskStatistics.objects.all())
        dates = [stat.date for stat in stats]

        expected_dates = [date(2024, 1, 20), date(2024, 1, 15), date(2024, 1, 10)]
        self.assertEqual(dates, expected_dates)

    def test_total_tasks_property(self):
        """Test total_tasks property calculation."""
        expected_total = 10 + 5 + 8 + 2 + 1  # Sum of all task counts
        self.assertEqual(self.stats.total_tasks, expected_total)

        # Test with zero counts
        zero_stats = TaskStatistics.objects.create(date=date(2024, 1, 16))
        self.assertEqual(zero_stats.total_tasks, 0)

    def test_success_rate_property(self):
        """Test success_rate property calculation."""
        # success_count=20, failure_count=6, so rate should be 20/26 * 100 = ~76.92%
        expected_rate = (20 / 26) * 100
        self.assertAlmostEqual(self.stats.success_rate, expected_rate, places=2)

        # Test with no completed tasks
        zero_stats = TaskStatistics.objects.create(date=date(2024, 1, 16))
        self.assertIsNone(zero_stats.success_rate)

        # Test with only successful tasks
        perfect_stats = TaskStatistics.objects.create(
            date=date(2024, 1, 17),
            success_count=10,
            failure_count=0
        )
        self.assertEqual(perfect_stats.success_rate, 100.0)


class DataPipelineModelRelationshipTests(TestCase):
    """Tests for data pipeline model relationships and foreign keys."""

    def setUp(self):
        """Set up test data with full relationship chain."""
        # Create location hierarchy
        self.admin0 = AdmLevel.objects.create(code="0", name="Country")
        self.admin1 = AdmLevel.objects.create(code="1", name="State")

        self.country = Location.objects.create(
            geo_id="SD",
            name="Sudan",
            admin_level=self.admin0
        )

        self.state = Location.objects.create(
            geo_id="SD_001",
            name="Khartoum",
            admin_level=self.admin1,
            parent=self.country
        )

        # Create source and variables
        self.source = Source.objects.create(
            name="ACLED",
            type="api",
            class_name="ACLEDSource"
        )

        self.fatalities_var = Variable.objects.create(
            source=self.source,
            name="Fatalities",
            code="fatalities",
            period="day",
            adm_level=1,
            type="quantitative"
        )

        self.events_var = Variable.objects.create(
            source=self.source,
            name="Events",
            code="events",
            period="day",
            adm_level=1,
            type="quantitative"
        )

    def test_source_to_variables_relationship(self):
        """Test Source to Variable relationship."""
        # Test forward relationship
        variables = self.source.variables.all()
        self.assertEqual(len(variables), 2)
        self.assertIn(self.fatalities_var, variables)
        self.assertIn(self.events_var, variables)

        # Test reverse relationship
        self.assertEqual(self.fatalities_var.source, self.source)
        self.assertEqual(self.events_var.source, self.source)

    def test_variable_to_data_relationship(self):
        """Test Variable to VariableData relationship."""
        # Create some data records
        VariableData.objects.create(
            variable=self.fatalities_var,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            period="day",
            adm_level=self.admin1,
            gid=self.state,
            value=10.0
        )

        VariableData.objects.create(
            variable=self.fatalities_var,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
            period="day",
            adm_level=self.admin1,
            gid=self.state,
            value=15.0
        )

        # Test forward relationship
        data_records = self.fatalities_var.data_records.all()
        self.assertEqual(len(data_records), 2)

        # Test reverse relationship
        for record in data_records:
            self.assertEqual(record.variable, self.fatalities_var)

    def test_location_to_variable_data_relationship(self):
        """Test Location to VariableData relationship."""
        # Create data for different variables but same location
        VariableData.objects.create(
            variable=self.fatalities_var,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            period="day",
            adm_level=self.admin1,
            gid=self.state,
            value=10.0
        )

        VariableData.objects.create(
            variable=self.events_var,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            period="day",
            adm_level=self.admin1,
            gid=self.state,
            value=3.0
        )

        # Check that location has data from multiple variables
        # Note: We need to access via the reverse relationship name
        # Since gid is the field name, Django creates variabledata_set as reverse manager
        data_for_location = VariableData.objects.filter(gid=self.state)
        self.assertEqual(len(data_for_location), 2)

    def test_cascade_delete_behavior(self):
        """Test cascade delete behavior across relationships."""
        # Create data record
        data_record = VariableData.objects.create(
            variable=self.fatalities_var,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            period="day",
            adm_level=self.admin1,
            gid=self.state,
            value=10.0
        )

        data_id = data_record.id
        variable_id = self.fatalities_var.id

        # Delete source should cascade to variables and their data
        self.source.delete()

        # Variable and its data should be deleted
        with self.assertRaises(Variable.DoesNotExist):
            Variable.objects.get(id=variable_id)

        with self.assertRaises(VariableData.DoesNotExist):
            VariableData.objects.get(id=data_id)

    def test_protect_delete_behavior(self):
        """Test PROTECT delete behavior."""
        # Create data record
        VariableData.objects.create(
            variable=self.fatalities_var,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            period="day",
            adm_level=self.admin1,
            gid=self.state,
            value=10.0
        )

        # Should not be able to delete location or admin level due to PROTECT
        with self.assertRaises(Exception):
            self.state.delete()

        with self.assertRaises(Exception):
            self.admin1.delete()

    def test_model_indexes_and_performance(self):
        """Test that model indexes are working for performance."""
        # Create multiple data records for performance testing
        records = []
        for i in range(10):
            records.append(VariableData(
                variable=self.fatalities_var,
                start_date=date(2024, 1, 1) + timedelta(days=i),
                end_date=date(2024, 1, 1) + timedelta(days=i),
                period="day",
                adm_level=self.admin1,
                gid=self.state,
                value=float(i)
            ))

        VariableData.objects.bulk_create(records)

        # These queries should be efficient due to indexes
        # Test variable + date range query (indexed)
        date_filtered = VariableData.objects.filter(
            variable=self.fatalities_var,
            start_date__gte=date(2024, 1, 5),
            end_date__lte=date(2024, 1, 8)
        )
        self.assertTrue(len(date_filtered) > 0)

        # Test location + variable query (indexed)
        location_filtered = VariableData.objects.filter(
            gid=self.state,
            variable=self.fatalities_var
        )
        self.assertEqual(len(location_filtered), 10)


class DataPipelineIntegrationTests(TestCase):
    """Integration tests for data pipeline functionality."""

    def setUp(self):
        """Set up comprehensive test scenario."""
        # Create location hierarchy
        self.admin1 = AdmLevel.objects.create(code="1", name="State")
        self.location = Location.objects.create(
            geo_id="SD_001",
            name="Khartoum",
            admin_level=self.admin1
        )

        # Create multiple sources
        self.acled_source = Source.objects.create(
            name="ACLED",
            description="Armed Conflict Location & Event Data Project",
            type="api",
            base_url="https://api.acleddata.com",
            class_name="ACLEDSource"
        )

        self.unhcr_source = Source.objects.create(
            name="UNHCR",
            description="UN High Commissioner for Refugees",
            type="api",
            base_url="https://api.unhcr.org",
            class_name="UNHCRSource"
        )

        # Create variables for each source
        self.acled_fatalities = Variable.objects.create(
            source=self.acled_source,
            name="Fatalities",
            code="fatalities",
            period="day",
            adm_level=1,
            type="quantitative",
            text="Daily conflict fatalities"
        )

        self.acled_events = Variable.objects.create(
            source=self.acled_source,
            name="Events",
            code="events",
            period="day",
            adm_level=1,
            type="quantitative",
            text="Daily conflict events"
        )

        self.unhcr_refugees = Variable.objects.create(
            source=self.unhcr_source,
            name="Refugees",
            code="refugees",
            period="month",
            adm_level=1,
            type="quantitative",
            text="Monthly refugee count"
        )

    def test_multi_source_data_workflow(self):
        """Test complete data workflow with multiple sources."""
        # Simulate data ingestion from multiple sources
        start_date = date(2024, 1, 1)

        # ACLED daily data
        for day in range(7):  # Week of data
            current_date = start_date + timedelta(days=day)

            # Fatalities data
            VariableData.objects.create(
                variable=self.acled_fatalities,
                start_date=current_date,
                end_date=current_date,
                period="day",
                adm_level=self.admin1,
                gid=self.location,
                value=float(5 + day)  # Increasing trend
            )

            # Events data
            VariableData.objects.create(
                variable=self.acled_events,
                start_date=current_date,
                end_date=current_date,
                period="day",
                adm_level=self.admin1,
                gid=self.location,
                value=float(2 + (day * 0.5))  # Slower increase
            )

        # UNHCR monthly data
        VariableData.objects.create(
            variable=self.unhcr_refugees,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            period="month",
            adm_level=self.admin1,
            gid=self.location,
            value=1500.0
        )

        # Verify data was created correctly
        self.assertEqual(VariableData.objects.count(), 15)  # 7 + 7 + 1

        # Test querying by source
        acled_data = VariableData.objects.filter(variable__source=self.acled_source)
        unhcr_data = VariableData.objects.filter(variable__source=self.unhcr_source)

        self.assertEqual(acled_data.count(), 14)  # 7 fatalities + 7 events
        self.assertEqual(unhcr_data.count(), 1)   # 1 refugee count

        # Test querying by location
        location_data = VariableData.objects.filter(gid=self.location)
        self.assertEqual(location_data.count(), 15)

        # Test querying by date range
        week_data = VariableData.objects.filter(
            start_date__gte=start_date,
            end_date__lte=start_date + timedelta(days=6)
        )
        self.assertEqual(week_data.count(), 14)  # Daily data only

    def test_data_aggregation_scenarios(self):
        """Test various data aggregation scenarios."""
        # Create data for aggregation testing
        base_date = date(2024, 1, 1)

        # Create 30 days of data
        daily_values = []
        for day in range(30):
            current_date = base_date + timedelta(days=day)
            value = 10 + (day % 7)  # Weekly pattern

            VariableData.objects.create(
                variable=self.acled_fatalities,
                start_date=current_date,
                end_date=current_date,
                period="day",
                adm_level=self.admin1,
                gid=self.location,
                value=value
            )
            daily_values.append(value)

        # Test aggregation queries
        from django.db.models import Avg, Count, Max, Min, Sum

        stats = VariableData.objects.filter(
            variable=self.acled_fatalities
        ).aggregate(
            total=Sum('value'),
            average=Avg('value'),
            maximum=Max('value'),
            minimum=Min('value'),
            count=Count('id')
        )

        expected_total = sum(daily_values)
        expected_avg = sum(daily_values) / len(daily_values)

        self.assertEqual(stats['total'], expected_total)
        self.assertAlmostEqual(stats['average'], expected_avg, places=2)
        self.assertEqual(stats['maximum'], max(daily_values))
        self.assertEqual(stats['minimum'], min(daily_values))
        self.assertEqual(stats['count'], 30)

    def test_task_statistics_integration(self):
        """Test TaskStatistics integration with actual task data."""
        # Create task statistics for different days
        dates = [date(2024, 1, i) for i in range(1, 8)]  # Week of data

        for i, stat_date in enumerate(dates):
            TaskStatistics.objects.create(
                date=stat_date,
                check_updates_count=5 + i,
                download_data_count=3 + i,
                process_data_count=2 + i,
                success_count=8 + (i * 2),
                failure_count=2 + (i % 3),  # Varying failure pattern
                avg_duration_seconds=30.0 + (i * 5.0),
                max_duration_seconds=60.0 + (i * 10.0)
            )

        # Test querying statistics
        stats = TaskStatistics.objects.all()
        self.assertEqual(len(stats), 7)

        # Test aggregation across time periods
        from django.db.models import Avg, Sum

        weekly_totals = TaskStatistics.objects.aggregate(
            total_checks=Sum('check_updates_count'),
            total_downloads=Sum('download_data_count'),
            total_processes=Sum('process_data_count'),
            avg_success_rate=Avg('success_count') / (Avg('success_count') + Avg('failure_count')) * 100
        )

        self.assertIsNotNone(weekly_totals['total_checks'])
        self.assertIsNotNone(weekly_totals['total_downloads'])
        self.assertIsNotNone(weekly_totals['total_processes'])

        # Test performance trends
        latest_stats = TaskStatistics.objects.first()  # Most recent due to ordering
        oldest_stats = TaskStatistics.objects.last()

        self.assertGreater(
            latest_stats.avg_duration_seconds,
            oldest_stats.avg_duration_seconds
        )

    @patch('data_pipeline.models.Source.objects')
    def test_error_handling_with_missing_data(self, mock_source_objects):
        """Test error handling when data relationships are missing."""
        # Test graceful handling of missing relationships
        mock_source_objects.get.side_effect = Source.DoesNotExist()

        # This should handle the missing source gracefully
        try:
            # In a real scenario, this might be part of a data loading process
            variables = Variable.objects.filter(source__name="NonExistent")
            self.assertEqual(len(variables), 0)
        except Source.DoesNotExist:
            self.fail("Should handle missing source gracefully")

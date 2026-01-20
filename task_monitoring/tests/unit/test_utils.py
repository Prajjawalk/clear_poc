"""Unit tests for task monitoring utility functions."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

from task_monitoring.utils import (
    format_time_until,
    get_next_run_time,
    get_readable_schedule,
)


class ScheduleFormattingTests(TestCase):
    """Tests for schedule formatting utilities."""

    def test_interval_schedule_formatting(self):
        """Test readable formatting of interval schedules."""
        test_cases = [
            # Standard intervals
            (1, "days", "Daily"),
            (7, "days", "Weekly"),
            (30, "days", "Monthly"),
            (1, "hours", "Hourly"),
            (15, "minutes", "Every 15 minutes"),
            (1, "minutes", "Every minute"),
            # Custom intervals
            (2, "days", "Every 2 days"),
            (3, "hours", "Every 3 hours"),
            (45, "minutes", "Every 45 minutes"),
        ]

        for every, period, expected in test_cases:
            with self.subTest(every=every, period=period):
                interval = IntervalSchedule(every=every, period=period)
                task = PeriodicTask(interval=interval, enabled=True)
                result = get_readable_schedule(task)
                self.assertEqual(result, expected)

    def test_seconds_interval_formatting(self):
        """Test readable formatting of second-based intervals."""
        test_cases = [
            # Common second intervals
            (86400, "seconds", "Daily"),  # 24 hours
            (604800, "seconds", "Weekly"),  # 7 days
            (3600, "seconds", "Hourly"),  # 1 hour
            (1800, "seconds", "Every 30 minutes"),  # 30 minutes
            (900, "seconds", "Every 15 minutes"),  # 15 minutes
            (300, "seconds", "Every 5 minutes"),  # 5 minutes
            (60, "seconds", "Every minute"),  # 1 minute
            # Custom second intervals
            (7200, "seconds", "Every 2 hours"),  # 2 hours
            (120, "seconds", "Every 2 minutes"),  # 2 minutes
            (45, "seconds", "Every 45 seconds"),  # 45 seconds
        ]

        for every, period, expected in test_cases:
            with self.subTest(every=every, period=period):
                interval = IntervalSchedule(every=every, period=period)
                task = PeriodicTask(interval=interval, enabled=True)
                result = get_readable_schedule(task)
                self.assertEqual(result, expected)

    def test_crontab_schedule_formatting(self):
        """Test readable formatting of crontab schedules."""
        test_cases = [
            # Daily patterns
            ("0", "6", "*", "*", "*", "Daily at 06:00"),
            ("30", "14", "*", "*", "*", "Daily at 14:30"),
            ("0", "0", "*", "*", "*", "Daily at midnight"),
            # Monthly patterns
            ("0", "2", "1", "*", "*", "Monthly at 02:00 on the 1st"),
            ("30", "3", "15", "*", "*", "Monthly at 03:30 on the 15th"),
            ("0", "12", "22", "*", "*", "Monthly at 12:00 on the 22nd"),
            ("0", "8", "3", "*", "*", "Monthly at 08:00 on the 3rd"),
            # Weekly patterns
            ("0", "10", "*", "*", "1", "Weekly at 10:00 on Monday"),
            ("0", "9", "*", "*", "0", "Weekly at 09:00 on Sunday"),
            ("30", "16", "*", "*", "5", "Weekly at 16:30 on Friday"),
            # Hourly patterns
            ("0", "*", "*", "*", "*", "Hourly at minute 00"),
            ("15", "*", "*", "*", "*", "Hourly at minute 15"),
            ("45", "*", "*", "*", "*", "Hourly at minute 45"),
            # Yearly patterns
            ("0", "12", "1", "1", "*", "Yearly at 12:00 on the 1st in January"),
            ("30", "9", "15", "6", "*", "Yearly at 09:30 on the 15th in June"),
        ]

        for minute, hour, day_of_month, month_of_year, day_of_week, expected in test_cases:
            with self.subTest(cron=f"{minute} {hour} {day_of_month} {month_of_year} {day_of_week}"):
                cron = CrontabSchedule(
                    minute=minute,
                    hour=hour,
                    day_of_month=day_of_month,
                    month_of_year=month_of_year,
                    day_of_week=day_of_week,
                )
                task = PeriodicTask(crontab=cron, enabled=True)
                result = get_readable_schedule(task)
                self.assertEqual(result, expected)

    def test_no_schedule_formatting(self):
        """Test formatting when no schedule is defined."""
        task = PeriodicTask(enabled=True)
        result = get_readable_schedule(task)
        self.assertEqual(result, "No schedule defined")


class NextRunTimeTests(TestCase):
    """Tests for next run time calculation."""

    def test_interval_next_run_calculation(self):
        """Test next run time calculation for interval schedules."""
        now = timezone.now()

        # Test daily interval
        interval = IntervalSchedule(every=1, period="days")
        task = PeriodicTask(interval=interval, enabled=True)
        task.last_run_at = now - timedelta(hours=12)

        next_run = get_next_run_time(task)
        self.assertIsNotNone(next_run)
        # Should be 12 hours from now (24 hours from last run)
        expected = task.last_run_at + timedelta(days=1)
        self.assertAlmostEqual(
            next_run.timestamp(),
            expected.timestamp(),
            delta=1  # Allow 1 second difference
        )

    def test_interval_next_run_no_last_run(self):
        """Test next run calculation when task has never run."""
        now = timezone.now()

        interval = IntervalSchedule(every=1, period="hours")
        task = PeriodicTask(interval=interval, enabled=True)
        task.last_run_at = None
        task.date_changed = now - timedelta(minutes=30)

        next_run = get_next_run_time(task)
        self.assertIsNotNone(next_run)
        # Should be 30 minutes from now (1 hour from date_changed)
        expected = task.date_changed + timedelta(hours=1)
        self.assertAlmostEqual(
            next_run.timestamp(),
            expected.timestamp(),
            delta=1
        )

    def test_disabled_task_next_run(self):
        """Test that disabled tasks return None for next run."""
        interval = IntervalSchedule(every=1, period="days")
        task = PeriodicTask(interval=interval, enabled=False)

        next_run = get_next_run_time(task)
        self.assertIsNone(next_run)

    def test_no_schedule_next_run(self):
        """Test that tasks without schedules return None."""
        task = PeriodicTask(enabled=True)

        next_run = get_next_run_time(task)
        self.assertIsNone(next_run)


class TimeFormattingTests(TestCase):
    """Tests for time until formatting."""

    def test_format_time_until(self):
        """Test human-readable time until formatting."""
        # Use specific test times to avoid timing issues
        base_time = timezone.now().replace(microsecond=0)

        test_cases = [
            (base_time + timedelta(seconds=30), "Less than a minute"),
            (base_time + timedelta(minutes=1, seconds=30), "In 1 minute"),
            (base_time + timedelta(minutes=45, seconds=30), "In 45 minutes"),
            (base_time + timedelta(hours=1, minutes=30), "In 1 hour"),
            (base_time + timedelta(hours=3, minutes=30), "In 3 hours"),
            (base_time + timedelta(days=1, hours=12), "In 1 day"),
            (base_time + timedelta(days=5, hours=12), "In 5 days"),
            (base_time + timedelta(weeks=1, days=3), "In 1 week"),
            (base_time + timedelta(weeks=3, days=3), "In 3 weeks"),
        ]

        for next_run, expected in test_cases:
            with self.subTest(next_run=next_run):
                # Mock timezone.now() to return our base_time
                with patch('task_monitoring.utils.timezone') as mock_timezone:
                    mock_timezone.now.return_value = base_time
                    result = format_time_until(next_run)
                    self.assertEqual(result, expected)

    def test_format_time_until_none(self):
        """Test formatting when next_run is None."""
        result = format_time_until(None)
        self.assertEqual(result, "Not scheduled")

    def test_format_time_until_overdue(self):
        """Test formatting when next_run is in the past."""
        past_time = timezone.now() - timedelta(hours=1)
        result = format_time_until(past_time)
        self.assertEqual(result, "Overdue")


class ScheduleUtilityIntegrationTests(TestCase):
    """Integration tests for schedule utilities working together."""

    def test_complete_schedule_processing(self):
        """Test complete schedule processing pipeline."""
        # Create a daily task
        interval = IntervalSchedule(every=1, period="days")
        task = PeriodicTask(
            name="Test Daily Task",
            interval=interval,
            enabled=True,
            last_run_at=timezone.now() - timedelta(hours=12)
        )

        # Test all utilities work together
        readable = get_readable_schedule(task)
        next_run = get_next_run_time(task)
        time_until = format_time_until(next_run)

        self.assertEqual(readable, "Daily")
        self.assertIsNotNone(next_run)
        self.assertIn("hour", time_until)  # Should be around 12 hours

    def test_crontab_complete_processing(self):
        """Test complete crontab schedule processing."""
        # Create a weekly task (Monday at 9 AM)
        cron = CrontabSchedule(
            minute="0",
            hour="9",
            day_of_month="*",
            month_of_year="*",
            day_of_week="1"
        )
        task = PeriodicTask(
            name="Weekly Monday Task",
            crontab=cron,
            enabled=True
        )

        # Test utilities
        readable = get_readable_schedule(task)
        next_run = get_next_run_time(task)
        time_until = format_time_until(next_run)

        self.assertEqual(readable, "Weekly at 09:00 on Monday")
        # next_run calculation for crontab is complex, just ensure it doesn't crash
        if next_run:
            self.assertIsInstance(time_until, str)
        else:
            self.assertEqual(time_until, "Not scheduled")

    def test_edge_cases(self):
        """Test edge cases and error conditions."""
        # Test with invalid/missing data
        task = PeriodicTask(enabled=True)

        readable = get_readable_schedule(task)
        next_run = get_next_run_time(task)
        time_until = format_time_until(next_run)

        self.assertEqual(readable, "No schedule defined")
        self.assertIsNone(next_run)
        self.assertEqual(time_until, "Not scheduled")

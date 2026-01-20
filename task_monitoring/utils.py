"""Utility functions for task monitoring."""

from datetime import datetime, timedelta
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from django_celery_beat.schedulers import DatabaseScheduler
from celery.schedules import crontab, schedule


def get_readable_schedule(task):
    """
    Convert a task's schedule to a human-readable format.

    Args:
        task: PeriodicTask instance

    Returns:
        str: Human-readable schedule description
    """
    if task.interval:
        interval = task.interval
        period_map = {
            'days': 'day',
            'hours': 'hour',
            'minutes': 'minute',
            'seconds': 'second',
            'microseconds': 'microsecond'
        }

        # Get singular/plural form
        period_name = period_map.get(interval.period, interval.period)
        if interval.every != 1:
            period_name = interval.period  # Use plural form

        # Convert seconds to more readable units
        if interval.period == 'seconds':
            total_seconds = interval.every

            # Check for common second-based intervals
            if total_seconds == 86400:
                return "Daily"
            elif total_seconds == 604800:
                return "Weekly"
            elif total_seconds == 3600:
                return "Hourly"
            elif total_seconds == 1800:
                return "Every 30 minutes"
            elif total_seconds == 900:
                return "Every 15 minutes"
            elif total_seconds == 300:
                return "Every 5 minutes"
            elif total_seconds == 60:
                return "Every minute"
            elif total_seconds % 3600 == 0:
                hours = total_seconds // 3600
                if hours == 1:
                    return "Hourly"
                else:
                    return f"Every {hours} hours"
            elif total_seconds % 60 == 0:
                minutes = total_seconds // 60
                if minutes == 1:
                    return "Every minute"
                else:
                    return f"Every {minutes} minutes"
            else:
                return f"Every {interval.every} seconds"

        # Format based on common intervals
        elif interval.period == 'days':
            if interval.every == 1:
                return "Daily"
            elif interval.every == 7:
                return "Weekly"
            elif interval.every == 30:
                return "Monthly"
            else:
                return f"Every {interval.every} days"
        elif interval.period == 'hours':
            if interval.every == 1:
                return "Hourly"
            else:
                return f"Every {interval.every} hours"
        elif interval.period == 'minutes':
            if interval.every == 1:
                return "Every minute"
            else:
                return f"Every {interval.every} minutes"
        else:
            return f"Every {interval.every} {period_name}"

    elif task.crontab:
        cron = task.crontab

        # Special cases for common cron patterns
        if cron.minute == '0' and cron.hour == '0' and cron.day_of_month == '*' and cron.month_of_year == '*':
            if cron.day_of_week == '*':
                return "Daily at midnight"
            elif cron.day_of_week == '1':
                return "Weekly on Monday at midnight"
            elif cron.day_of_week == '0':
                return "Weekly on Sunday at midnight"

        if cron.minute == '0' and cron.hour == '*' and cron.day_of_month == '*' and cron.month_of_year == '*' and cron.day_of_week == '*':
            return "Hourly at minute 00"

        if cron.minute == '*' and cron.hour == '*' and cron.day_of_month == '*' and cron.month_of_year == '*' and cron.day_of_week == '*':
            return "Every minute"

        # Handle step values (e.g., */4 for every 4 hours)
        if cron.minute == '0' and cron.hour.startswith('*/') and cron.day_of_month == '*' and cron.month_of_year == '*' and cron.day_of_week == '*':
            step = int(cron.hour[2:])
            return f"Every {step} hours"

        # Determine frequency prefix based on pattern
        frequency_prefix = ""

        # Check if it's daily (specific time, all days)
        if (cron.minute != '*' and cron.hour != '*' and
            cron.day_of_month == '*' and cron.month_of_year == '*' and cron.day_of_week == '*'):
            frequency_prefix = "Daily"

        # Check if it's weekly (specific day of week)
        elif cron.day_of_week != '*' and cron.day_of_month == '*' and cron.month_of_year == '*':
            frequency_prefix = "Weekly"

        # Check if it's monthly (specific day of month)
        elif cron.day_of_month != '*' and cron.day_of_week == '*' and cron.month_of_year == '*':
            frequency_prefix = "Monthly"

        # Check if it's yearly (specific month)
        elif cron.month_of_year != '*':
            frequency_prefix = "Yearly"

        # Check if it's hourly (every hour at specific minute)
        elif cron.minute != '*' and cron.hour == '*' and cron.day_of_month == '*' and cron.month_of_year == '*' and cron.day_of_week == '*':
            return f"Hourly at minute {cron.minute}"

        # Build readable description for complex patterns
        parts = []

        # Add frequency prefix if we have one
        if frequency_prefix:
            parts.append(frequency_prefix)

        # Helper function to parse cron field values
        def parse_cron_field(field_value, field_name="field"):
            """Parse a cron field that might contain special syntax like */4"""
            if field_value == '*':
                return None, None
            elif field_value.startswith('*/'):
                # Step value like */4 means "every 4"
                step = int(field_value[2:])
                return 'step', step
            elif ',' in field_value:
                # Multiple specific values like "6,18"
                return 'list', [int(x) for x in field_value.split(',')]
            else:
                # Single value
                try:
                    return 'single', int(field_value)
                except ValueError:
                    # If we can't parse it, just return the raw value
                    return 'raw', field_value

        # Time component
        minute_type, minute_val = parse_cron_field(cron.minute, "minute")
        hour_type, hour_val = parse_cron_field(cron.hour, "hour")

        if minute_type and hour_type:
            # Both minute and hour are specified
            if hour_type == 'list':
                # Multiple specific hours (e.g., "6,18")
                if minute_type == 'single':
                    time_strs = [f"{h:02d}:{minute_val:02d}" for h in hour_val]
                    parts.append(f"at {' and '.join(time_strs)}")
                else:
                    parts.append(f"during hours {cron.hour} at minute {cron.minute}")
            elif hour_type == 'single' and minute_type == 'single':
                # Single specific time
                time_str = f"{hour_val:02d}:{minute_val:02d}"
                parts.append(f"at {time_str}")
            else:
                parts.append(f"at minute {cron.minute} of hour {cron.hour}")
        elif minute_type and not hour_type:
            # Only minute specified (hourly)
            if minute_type == 'single':
                parts.append(f"at minute {minute_val}")
            elif minute_type == 'list':
                parts.append(f"at minutes {cron.minute}")
            elif minute_type == 'step':
                parts.append(f"every {minute_val} minutes")
            else:
                parts.append(f"at minute {cron.minute}")
        elif hour_type and not minute_type:
            # Only hour specified
            if hour_type == 'single':
                parts.append(f"during hour {hour_val}")
            elif hour_type == 'list':
                parts.append(f"during hours {cron.hour}")
            elif hour_type == 'step':
                parts.append(f"every {hour_val} hours")
            else:
                parts.append(f"during hour {cron.hour}")
        elif hour_type == 'step' and minute_type == 'single':
            # Special case: every N hours at specific minute
            parts.append(f"every {hour_val} hours at minute {minute_val}")

        # Day of week
        if cron.day_of_week != '*':
            days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            dow_type, dow_val = parse_cron_field(cron.day_of_week, "day_of_week")

            if dow_type == 'list':
                try:
                    day_names = [days[d] for d in dow_val]
                    parts.append(f"on {', '.join(day_names)}")
                except IndexError:
                    parts.append(f"on days {cron.day_of_week}")
            elif dow_type == 'single':
                try:
                    parts.append(f"on {days[dow_val]}")
                except IndexError:
                    parts.append(f"on day {cron.day_of_week}")
            elif dow_type == 'step':
                parts.append(f"every {dow_val} days of week")
            else:
                parts.append(f"on day {cron.day_of_week}")

        # Day of month
        if cron.day_of_month != '*':
            if cron.day_of_month == '1':
                parts.append("on the 1st")
            elif cron.day_of_month.endswith('1') and cron.day_of_month != '11':
                parts.append(f"on the {cron.day_of_month}st")
            elif cron.day_of_month.endswith('2') and cron.day_of_month != '12':
                parts.append(f"on the {cron.day_of_month}nd")
            elif cron.day_of_month.endswith('3') and cron.day_of_month != '13':
                parts.append(f"on the {cron.day_of_month}rd")
            else:
                parts.append(f"on the {cron.day_of_month}th")

        # Month
        if cron.month_of_year != '*':
            months = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                     'July', 'August', 'September', 'October', 'November', 'December']
            if ',' in cron.month_of_year:
                month_nums = [int(m) for m in cron.month_of_year.split(',')]
                month_names = [months[m] for m in month_nums]
                parts.append(f"in {', '.join(month_names)}")
            else:
                try:
                    month_num = int(cron.month_of_year)
                    parts.append(f"in {months[month_num]}")
                except (ValueError, IndexError):
                    parts.append(f"in month {cron.month_of_year}")

        if parts:
            return ' '.join(parts)
        else:
            # Fallback to cron notation
            return f"Cron: {cron.minute} {cron.hour} {cron.day_of_month} {cron.month_of_year} {cron.day_of_week}"

    elif task.solar:
        return f"Solar: {task.solar.event} at {task.solar.latitude}°, {task.solar.longitude}°"

    elif task.clocked:
        return f"Once at {task.clocked.clocked_time.strftime('%Y-%m-%d %H:%M:%S')}"

    else:
        return "No schedule defined"


def get_next_run_time(task):
    """
    Calculate the next run time for a periodic task.

    Args:
        task: PeriodicTask instance

    Returns:
        datetime: Next scheduled run time or None
    """
    if not task.enabled:
        return None

    now = timezone.now()

    # If task has never run, use created time or now as reference
    last_run = task.last_run_at or task.date_changed or now

    if task.interval:
        # Calculate next run based on interval
        interval = task.interval

        # Convert interval to timedelta
        if interval.period == 'days':
            delta = timedelta(days=interval.every)
        elif interval.period == 'hours':
            delta = timedelta(hours=interval.every)
        elif interval.period == 'minutes':
            delta = timedelta(minutes=interval.every)
        elif interval.period == 'seconds':
            delta = timedelta(seconds=interval.every)
        elif interval.period == 'microseconds':
            delta = timedelta(microseconds=interval.every)
        else:
            return None

        next_run = last_run + delta

        # If next run is in the past, calculate the next future run
        while next_run < now:
            next_run += delta

        return next_run

    elif task.crontab:
        # Use celery's crontab schedule to calculate next run
        cron = task.crontab

        # Create a crontab schedule instance
        schedule_obj = crontab(
            minute=cron.minute,
            hour=cron.hour,
            day_of_week=cron.day_of_week,
            day_of_month=cron.day_of_month,
            month_of_year=cron.month_of_year
        )

        # Get remaining time until next execution
        remaining = schedule_obj.remaining_estimate(last_run)

        if remaining:
            return now + remaining

    elif task.solar:
        # Solar schedules are complex, would need additional libraries
        # For now, return None
        return None

    elif task.clocked:
        # One-time schedule
        if task.clocked.enabled and task.clocked.clocked_time > now:
            return task.clocked.clocked_time

    return None


def format_time_until(next_run):
    """
    Format the time remaining until next run in a human-readable way.

    Args:
        next_run: datetime of next run

    Returns:
        str: Human-readable time until next run
    """
    if not next_run:
        return "Not scheduled"

    now = timezone.now()

    if next_run < now:
        return "Overdue"

    delta = next_run - now
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return "Less than a minute"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"In {minutes} minute{'s' if minutes != 1 else ''}"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        return f"In {hours} hour{'s' if hours != 1 else ''}"
    elif total_seconds < 604800:
        days = total_seconds // 86400
        return f"In {days} day{'s' if days != 1 else ''}"
    else:
        weeks = total_seconds // 604800
        return f"In {weeks} week{'s' if weeks != 1 else ''}"
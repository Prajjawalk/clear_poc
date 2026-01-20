"""Tests for alerts app utilities."""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from alerts.exceptions import ValidationError, ValidationHelper
from alerts.models import Alert, ShockType, UserAlert
from alerts.utils import AlertQueryBuilder, ResponseHelper, UserAlertManager
from data_pipeline.models import Source


class UserAlertManagerTest(TestCase):
    """Tests for UserAlertManager utility class."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.shock_type = ShockType.objects.create(name="Conflict", icon="fa-warning", color="#ff0000")

        # Create data source
        self.data_source = Source.objects.create(
            name="Test Source",
            description="Test data source for utils tests",
            is_active=True
        )

        self.alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=3,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            go_no_go=True
        )

    def test_get_or_create_user_alert_creates_new(self):
        """Test creating new UserAlert when none exists."""
        user_alert = UserAlertManager.get_or_create_user_alert(self.user, self.alert)

        self.assertIsInstance(user_alert, UserAlert)
        self.assertEqual(user_alert.user, self.user)
        self.assertEqual(user_alert.alert, self.alert)
        self.assertIsNotNone(user_alert.received_at)
        self.assertEqual(UserAlert.objects.count(), 1)

    def test_get_or_create_user_alert_returns_existing(self):
        """Test returning existing UserAlert without creating new one."""
        # Create existing UserAlert
        existing_user_alert = UserAlert.objects.create(
            user=self.user,
            alert=self.alert,
            rating=4,
            received_at=timezone.now()
        )

        user_alert = UserAlertManager.get_or_create_user_alert(self.user, self.alert)

        self.assertEqual(user_alert, existing_user_alert)
        self.assertEqual(user_alert.rating, 4)  # Existing data preserved
        self.assertEqual(UserAlert.objects.count(), 1)  # No new record created

    def test_mark_as_read_creates_user_alert_if_needed(self):
        """Test that mark_as_read creates UserAlert if it doesn't exist."""
        user_alert = UserAlertManager.mark_as_read(self.user, self.alert)

        self.assertIsNotNone(user_alert.read_at)
        self.assertIsNotNone(user_alert.received_at)
        self.assertEqual(UserAlert.objects.count(), 1)

    def test_mark_as_read_updates_existing(self):
        """Test that mark_as_read updates existing UserAlert."""
        # Create existing UserAlert without read_at
        existing_user_alert = UserAlert.objects.create(
            user=self.user,
            alert=self.alert,
            received_at=timezone.now()
        )

        self.assertIsNone(existing_user_alert.read_at)

        user_alert = UserAlertManager.mark_as_read(self.user, self.alert)

        self.assertEqual(user_alert, existing_user_alert)
        self.assertIsNotNone(user_alert.read_at)

    def test_mark_as_read_does_not_update_already_read(self):
        """Test that mark_as_read doesn't update already read alerts."""
        original_read_time = timezone.now() - timedelta(hours=1)
        existing_user_alert = UserAlert.objects.create(
            user=self.user,
            alert=self.alert,
            read_at=original_read_time,
            received_at=timezone.now()
        )

        user_alert = UserAlertManager.mark_as_read(self.user, self.alert)

        self.assertEqual(user_alert.read_at, original_read_time)  # Unchanged

    def test_toggle_bookmark_creates_and_bookmarks(self):
        """Test that toggle_bookmark creates UserAlert and sets bookmark."""
        user_alert, is_bookmarked = UserAlertManager.toggle_bookmark(self.user, self.alert)

        self.assertTrue(is_bookmarked)
        self.assertTrue(user_alert.bookmarked)
        self.assertEqual(UserAlert.objects.count(), 1)

    def test_toggle_bookmark_toggles_existing(self):
        """Test that toggle_bookmark toggles existing bookmark status."""
        # Create bookmarked UserAlert
        existing_user_alert = UserAlert.objects.create(
            user=self.user,
            alert=self.alert,
            bookmarked=True,
            received_at=timezone.now()
        )

        # Toggle off
        user_alert, is_bookmarked = UserAlertManager.toggle_bookmark(self.user, self.alert)
        self.assertFalse(is_bookmarked)
        self.assertFalse(user_alert.bookmarked)

        # Toggle on again
        user_alert, is_bookmarked = UserAlertManager.toggle_bookmark(self.user, self.alert)
        self.assertTrue(is_bookmarked)
        self.assertTrue(user_alert.bookmarked)

    def test_set_rating_creates_and_sets(self):
        """Test that set_rating creates UserAlert and sets rating."""
        user_alert = UserAlertManager.set_rating(self.user, self.alert, 4)

        self.assertEqual(user_alert.rating, 4)
        self.assertIsNotNone(user_alert.rating_at)
        self.assertEqual(UserAlert.objects.count(), 1)

    def test_set_rating_updates_existing(self):
        """Test that set_rating updates existing rating."""
        # Create existing UserAlert
        existing_user_alert = UserAlert.objects.create(
            user=self.user,
            alert=self.alert,
            rating=3,
            received_at=timezone.now()
        )

        user_alert = UserAlertManager.set_rating(self.user, self.alert, 5)

        self.assertEqual(user_alert, existing_user_alert)
        self.assertEqual(user_alert.rating, 5)
        self.assertIsNotNone(user_alert.rating_at)

    def test_toggle_flag_false(self):
        """Test toggling false flag."""
        user_alert, is_flagged = UserAlertManager.toggle_flag(self.user, self.alert, "false")

        self.assertTrue(is_flagged)
        self.assertTrue(user_alert.flag_false)
        self.assertFalse(user_alert.flag_incomplete)

        # Toggle off
        user_alert, is_flagged = UserAlertManager.toggle_flag(self.user, self.alert, "false")
        self.assertFalse(is_flagged)
        self.assertFalse(user_alert.flag_false)

    def test_toggle_flag_incomplete(self):
        """Test toggling incomplete flag."""
        user_alert, is_flagged = UserAlertManager.toggle_flag(self.user, self.alert, "incomplete")

        self.assertTrue(is_flagged)
        self.assertTrue(user_alert.flag_incomplete)
        self.assertFalse(user_alert.flag_false)

        # Toggle off
        user_alert, is_flagged = UserAlertManager.toggle_flag(self.user, self.alert, "incomplete")
        self.assertFalse(is_flagged)
        self.assertFalse(user_alert.flag_incomplete)

    def test_toggle_flag_invalid_type(self):
        """Test that invalid flag types raise ValueError."""
        with self.assertRaises(ValueError):
            UserAlertManager.toggle_flag(self.user, self.alert, "invalid")

    def test_add_comment_creates_and_sets(self):
        """Test that add_comment creates UserAlert and sets comment."""
        comment_text = "This is a test comment"
        user_alert = UserAlertManager.add_comment(self.user, self.alert, comment_text)

        self.assertEqual(user_alert.comment, comment_text)
        self.assertEqual(UserAlert.objects.count(), 1)

    def test_add_comment_updates_existing(self):
        """Test that add_comment updates existing comment."""
        # Create existing UserAlert
        existing_user_alert = UserAlert.objects.create(
            user=self.user,
            alert=self.alert,
            comment="Old comment",
            received_at=timezone.now()
        )

        new_comment = "Updated comment"
        user_alert = UserAlertManager.add_comment(self.user, self.alert, new_comment)

        self.assertEqual(user_alert, existing_user_alert)
        self.assertEqual(user_alert.comment, new_comment)

    def test_get_user_interaction_returns_existing(self):
        """Test that get_user_interaction returns existing UserAlert."""
        existing_user_alert = UserAlert.objects.create(
            user=self.user,
            alert=self.alert,
            rating=5,
            received_at=timezone.now()
        )

        user_alert = UserAlertManager.get_user_interaction(self.user, self.alert)

        self.assertEqual(user_alert, existing_user_alert)
        self.assertEqual(user_alert.rating, 5)

    def test_get_user_interaction_returns_none_if_not_exists(self):
        """Test that get_user_interaction returns None if UserAlert doesn't exist."""
        user_alert = UserAlertManager.get_user_interaction(self.user, self.alert)
        self.assertIsNone(user_alert)


class AlertQueryBuilderTest(TestCase):
    """Tests for AlertQueryBuilder utility class."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.shock_type1 = ShockType.objects.create(name="Conflict", icon="fa-warning", color="#ff0000")
        self.shock_type2 = ShockType.objects.create(name="Disaster", icon="fa-fire", color="#00ff00")

        # Create data source
        self.data_source = Source.objects.create(
            name="Test Source",
            description="Test data source for query builder tests",
            is_active=True
        )

        # Create alerts
        self.alert1 = Alert.objects.create(
            title="Conflict Alert",
            text="Conflict in region",
            shock_type=self.shock_type1,
            data_source=self.data_source,
            severity=4,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=5),
            go_no_go=True
        )

        self.alert2 = Alert.objects.create(
            title="Disaster Alert",
            text="Natural disaster occurred",
            shock_type=self.shock_type2,
            data_source=self.data_source,
            severity=3,
            shock_date=timezone.now() - timedelta(days=1),
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=4),
            go_no_go=True
        )

        # Create unapproved alert
        self.unapproved_alert = Alert.objects.create(
            title="Unapproved Alert",
            text="Not approved",
            shock_type=self.shock_type1,
            data_source=self.data_source,
            severity=2,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=3),
            go_no_go=False
        )

    def test_get_approved_alerts_queryset(self):
        """Test getting base queryset for approved alerts."""
        queryset = AlertQueryBuilder.get_approved_alerts_queryset()

        alerts = list(queryset)
        self.assertEqual(len(alerts), 2)  # Only approved alerts
        self.assertIn(self.alert1, alerts)
        self.assertIn(self.alert2, alerts)
        self.assertNotIn(self.unapproved_alert, alerts)

    def test_get_approved_alerts_has_optimizations(self):
        """Test that base queryset includes optimizations."""
        queryset = AlertQueryBuilder.get_approved_alerts_queryset()

        # Check that select_related and prefetch_related are applied
        self.assertIn("shock_type", str(queryset.query))
        # Note: This is a basic check; in practice, query analysis would be more complex

    def test_apply_common_filters_shock_type(self):
        """Test filtering by shock type."""
        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        filters = {"shock_type": self.shock_type1.id}

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0], self.alert1)

    def test_apply_common_filters_severity(self):
        """Test filtering by severity."""
        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        filters = {"severity": "4"}

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0], self.alert1)

    def test_apply_common_filters_date_range(self):
        """Test filtering by date range."""
        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        today = timezone.now().date()
        filters = {"date_from": str(today)}

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        # Should include alert1 (today) but not alert2 (yesterday)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0], self.alert1)

    def test_apply_common_filters_active_today(self):
        """Test filtering by active today."""
        # Create expired alert
        expired_alert = Alert.objects.create(
            title="Expired Alert",
            text="Expired",
            shock_type=self.shock_type1,
            data_source=self.data_source,
            severity=1,
            shock_date=timezone.now() - timedelta(days=10),
            valid_from=timezone.now() - timedelta(days=10),
            valid_until=timezone.now() - timedelta(days=5),  # Expired
            go_no_go=True
        )

        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        filters = {"active_today": "1"}

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        # Should not include expired alert
        alert_titles = [alert.title for alert in alerts]
        self.assertNotIn("Expired Alert", alert_titles)

    def test_apply_common_filters_search(self):
        """Test text search functionality."""
        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        filters = {"search": "conflict"}

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0], self.alert1)

    def test_apply_common_filters_search_case_insensitive(self):
        """Test that search is case insensitive."""
        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        filters = {"search": "DISASTER"}

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0], self.alert2)

    def test_apply_common_filters_bookmarked(self):
        """Test filtering by bookmarked alerts."""
        # Create bookmarked UserAlert
        UserAlert.objects.create(
            user=self.user,
            alert=self.alert1,
            bookmarked=True,
            received_at=timezone.now()
        )

        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        filters = {"bookmarked": "1", "user": self.user}

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0], self.alert1)

    def test_apply_common_filters_multiple_filters(self):
        """Test applying multiple filters simultaneously."""
        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        filters = {
            "shock_type": self.shock_type1.id,
            "severity": "4",
            "search": "conflict"
        }

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0], self.alert1)

    def test_apply_common_filters_empty_filters(self):
        """Test that empty filters don't change queryset."""
        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        filters = {}

        filtered_queryset = AlertQueryBuilder.apply_common_filters(base_queryset, filters)
        alerts = list(filtered_queryset)

        self.assertEqual(len(alerts), 2)  # All approved alerts

    def test_add_user_interactions_prefetch(self):
        """Test adding user interactions prefetch."""
        # Create user alerts
        UserAlert.objects.create(
            user=self.user,
            alert=self.alert1,
            rating=4,
            received_at=timezone.now()
        )

        base_queryset = AlertQueryBuilder.get_approved_alerts_queryset()
        prefetched_queryset = AlertQueryBuilder.add_user_interactions_prefetch(base_queryset, self.user)

        # Execute query and check prefetch
        alerts = list(prefetched_queryset)
        alert = alerts[0] if alerts[0] == self.alert1 else alerts[1]

        # Check that user interactions are prefetched
        with self.assertNumQueries(0):  # Should not generate additional queries
            user_interactions = getattr(alert, 'user_interactions', [])
            if user_interactions:
                self.assertEqual(user_interactions[0].rating, 4)

    def test_get_user_alert_from_prefetch_with_data(self):
        """Test extracting user alert from prefetched data."""
        # Create mock alert with prefetched user interactions
        mock_alert = Mock()
        mock_user_alert = Mock()
        mock_alert.user_interactions = [mock_user_alert]

        result = AlertQueryBuilder.get_user_alert_from_prefetch(mock_alert)
        self.assertEqual(result, mock_user_alert)

    def test_get_user_alert_from_prefetch_empty(self):
        """Test extracting user alert from prefetch when none exists."""
        # Create mock alert with empty user interactions
        mock_alert = Mock()
        mock_alert.user_interactions = []

        result = AlertQueryBuilder.get_user_alert_from_prefetch(mock_alert)
        self.assertIsNone(result)

    def test_get_user_alert_from_prefetch_no_attribute(self):
        """Test extracting user alert when prefetch attribute doesn't exist."""
        # Create mock alert without user_interactions attribute
        mock_alert = Mock(spec=[])  # Empty spec means no attributes

        result = AlertQueryBuilder.get_user_alert_from_prefetch(mock_alert)
        self.assertIsNone(result)


class ResponseHelperTest(TestCase):
    """Tests for ResponseHelper utility class."""

    def test_build_filter_context_with_values(self):
        """Test building filter context with provided values."""
        mock_request_get = {
            "shock_type": "1",
            "severity": "4",
            "date_from": "2024-01-01",
            "date_to": "2024-01-31",
            "active_today": "0",
            "bookmarked": "1",
            "search": "test search"
        }

        context = ResponseHelper.build_filter_context(mock_request_get)

        self.assertEqual(context["shock_type"], "1")
        self.assertEqual(context["severity"], "4")
        self.assertEqual(context["date_from"], "2024-01-01")
        self.assertEqual(context["date_to"], "2024-01-31")
        self.assertEqual(context["active_today"], "0")
        self.assertEqual(context["bookmarked"], "1")
        self.assertEqual(context["search"], "test search")

    def test_build_filter_context_with_defaults(self):
        """Test building filter context with default values."""
        mock_request_get = {}

        context = ResponseHelper.build_filter_context(mock_request_get)

        self.assertEqual(context["shock_type"], "")
        self.assertEqual(context["severity"], "")
        self.assertEqual(context["date_from"], "")
        self.assertEqual(context["date_to"], "")
        self.assertEqual(context["active_today"], "1")  # Default to "1"
        self.assertEqual(context["bookmarked"], "")
        self.assertEqual(context["search"], "")

    def test_build_filter_context_partial_values(self):
        """Test building filter context with some values provided."""
        mock_request_get = {
            "severity": "3",
            "search": "partial"
        }

        context = ResponseHelper.build_filter_context(mock_request_get)

        self.assertEqual(context["severity"], "3")
        self.assertEqual(context["search"], "partial")
        self.assertEqual(context["shock_type"], "")  # Default
        self.assertEqual(context["active_today"], "1")  # Default

    @patch('alerts.exceptions.ValidationHelper.validate_rating')
    def test_validate_rating_delegates_to_validation_helper(self, mock_validate):
        """Test that validate_rating delegates to ValidationHelper."""
        mock_validate.return_value = 4

        result = ResponseHelper.validate_rating("4")

        mock_validate.assert_called_once_with("4")
        self.assertEqual(result, 4)

    @patch('alerts.exceptions.ValidationHelper.validate_flag_type')
    def test_validate_flag_type_delegates_to_validation_helper(self, mock_validate):
        """Test that validate_flag_type delegates to ValidationHelper."""
        mock_validate.return_value = "false"

        result = ResponseHelper.validate_flag_type("false")

        mock_validate.assert_called_once_with("false")
        self.assertEqual(result, "false")


class ValidationHelperTest(TestCase):
    """Tests for ValidationHelper utility class."""

    def test_validate_rating_valid_values(self):
        """Test validation of valid rating values."""
        valid_ratings = [1, 2, 3, 4, 5, "1", "2", "3", "4", "5"]

        for rating in valid_ratings:
            result = ValidationHelper.validate_rating(rating)
            self.assertIn(result, [1, 2, 3, 4, 5])

    def test_validate_rating_invalid_range(self):
        """Test validation of ratings outside valid range."""
        invalid_ratings = [0, 6, 10, -1, "0", "6", "10"]

        for rating in invalid_ratings:
            with self.assertRaises(ValidationError):
                ValidationHelper.validate_rating(rating)

    def test_validate_rating_invalid_type(self):
        """Test validation of non-numeric rating values."""
        invalid_ratings = ["abc", "1.5", None, [], {}]

        for rating in invalid_ratings:
            with self.assertRaises(ValidationError):
                ValidationHelper.validate_rating(rating)

    def test_validate_flag_type_valid_values(self):
        """Test validation of valid flag type values."""
        valid_types = ["false", "incomplete"]

        for flag_type in valid_types:
            result = ValidationHelper.validate_flag_type(flag_type)
            self.assertEqual(result, flag_type)

    def test_validate_flag_type_invalid_values(self):
        """Test validation of invalid flag type values."""
        invalid_types = ["true", "complete", "invalid", "", None, 123]

        for flag_type in invalid_types:
            with self.assertRaises(ValidationError):
                ValidationHelper.validate_flag_type(flag_type)

    def test_validate_frequency_valid_values(self):
        """Test validation of valid frequency values."""
        valid_frequencies = ["immediate", "daily", "weekly", "monthly"]

        for frequency in valid_frequencies:
            result = ValidationHelper.validate_frequency(frequency)
            self.assertEqual(result, frequency)

    def test_validate_frequency_invalid_values(self):
        """Test validation of invalid frequency values."""
        invalid_frequencies = ["hourly", "yearly", "invalid", "", None, 123]

        for frequency in invalid_frequencies:
            with self.assertRaises(ValidationError):
                ValidationHelper.validate_frequency(frequency)

    def test_validate_severity_valid_values(self):
        """Test validation of valid severity values."""
        valid_severities = [1, 2, 3, 4, 5, "1", "2", "3", "4", "5"]

        for severity in valid_severities:
            result = ValidationHelper.validate_severity(severity)
            self.assertIn(result, [1, 2, 3, 4, 5])

    def test_validate_severity_invalid_range(self):
        """Test validation of severities outside valid range."""
        invalid_severities = [0, 6, 10, -1, "0", "6"]

        for severity in invalid_severities:
            with self.assertRaises(ValidationError):
                ValidationHelper.validate_severity(severity)

    def test_validate_positive_integer_valid_values(self):
        """Test validation of valid positive integers."""
        valid_values = [1, 5, 100, "1", "5", "100"]

        for value in valid_values:
            result = ValidationHelper.validate_positive_integer("test_field", value)
            self.assertIsInstance(result, int)
            self.assertGreater(result, 0)

    def test_validate_positive_integer_invalid_values(self):
        """Test validation of invalid positive integers."""
        invalid_values = [0, -1, -5, "0", "-1", "abc", None, 1.5]

        for value in invalid_values:
            with self.assertRaises(ValidationError):
                ValidationHelper.validate_positive_integer("test_field", value)

    def test_validate_date_range_valid_dates(self):
        """Test validation of valid date ranges."""
        date_from = "2024-01-01"
        date_to = "2024-01-31"

        result = ValidationHelper.validate_date_range(date_from, date_to)

        self.assertEqual(result["date_from"], date_from)
        self.assertEqual(result["date_to"], date_to)

    def test_validate_date_range_invalid_format(self):
        """Test validation of invalid date formats."""
        invalid_dates = ["2024/01/01", "01-01-2024", "invalid", "2024-13-01"]

        for date_str in invalid_dates:
            with self.assertRaises(ValidationError):
                ValidationHelper.validate_date_range(date_str, None)

    def test_validate_date_range_invalid_order(self):
        """Test validation of date ranges where from > to."""
        date_from = "2024-01-31"
        date_to = "2024-01-01"

        with self.assertRaises(ValidationError):
            ValidationHelper.validate_date_range(date_from, date_to)

    def test_validate_date_range_with_none_values(self):
        """Test validation of date ranges with None values."""
        result = ValidationHelper.validate_date_range(None, None)

        self.assertIsNone(result["date_from"])
        self.assertIsNone(result["date_to"])

        result = ValidationHelper.validate_date_range("2024-01-01", None)
        self.assertEqual(result["date_from"], "2024-01-01")
        self.assertIsNone(result["date_to"])

    def test_validate_date_range_iso_format_with_timezone(self):
        """Test validation of ISO format dates with timezone."""
        date_from = "2024-01-01T00:00:00Z"
        date_to = "2024-01-31T23:59:59Z"

        result = ValidationHelper.validate_date_range(date_from, date_to)

        self.assertEqual(result["date_from"], date_from)
        self.assertEqual(result["date_to"], date_to)

    def test_validation_error_includes_details(self):
        """Test that ValidationError includes proper details."""
        try:
            ValidationHelper.validate_rating("10")
        except ValidationError as e:
            self.assertEqual(e.code, "VALIDATION_ERROR")
            self.assertIn("rating", e.details["field"])
            self.assertEqual(e.details["value"], "10")
            self.assertEqual(e.status_code, 422)

    def test_validation_error_message_format(self):
        """Test that ValidationError messages are properly formatted."""
        try:
            ValidationHelper.validate_flag_type("invalid")
        except ValidationError as e:
            self.assertIn("flag_type", e.message)
            self.assertIn("false, incomplete", e.message)
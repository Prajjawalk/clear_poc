"""Tests for alert models."""

import re
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.template import Context, Template
from django.test import TestCase
from django.utils import timezone

from alerts.models import Alert, EmailTemplate, ShockType, Subscription, UserAlert
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class ShockTypeModelTest(TestCase):
    """Tests for ShockType model."""

    def setUp(self):
        """Set up test data."""
        self.shock_type = ShockType.objects.create(
            name="Conflict",
            icon="⚔️",
            color="#dc3545"
        )

    def test_shock_type_creation(self):
        """Test ShockType creation."""
        self.assertEqual(self.shock_type.name, "Conflict")
        self.assertEqual(self.shock_type.icon, "⚔️")
        self.assertEqual(self.shock_type.color, "#dc3545")
        self.assertIsNotNone(self.shock_type.created_at)
        self.assertIsNotNone(self.shock_type.updated_at)

    def test_shock_type_str(self):
        """Test ShockType string representation."""
        self.assertEqual(str(self.shock_type), "Conflict")

    def test_auto_generated_css_class(self):
        """Test automatic CSS class generation."""
        shock_type = ShockType.objects.create(
            name="Natural Disasters",
            icon="🌪️"
        )
        self.assertEqual(shock_type.css_class, "natural-disasters")

    def test_custom_css_class(self):
        """Test custom CSS class is preserved."""
        shock_type = ShockType.objects.create(
            name="Economic Crisis",
            css_class="custom-crisis"
        )
        self.assertEqual(shock_type.css_class, "custom-crisis")

    def test_css_class_special_characters(self):
        """Test CSS class generation with special characters."""
        shock_type = ShockType.objects.create(
            name="War & Conflict (2024)",
            icon="⚔️"
        )
        # Should remove special chars and keep only alphanumeric and hyphens
        self.assertEqual(shock_type.css_class, "war--conflict-2024")

    def test_background_css_class_property(self):
        """Test background CSS class property."""
        self.assertEqual(self.shock_type.background_css_class, "bg-conflict")

    def test_shock_type_unique_name(self):
        """Test that shock type names must be unique."""
        with self.assertRaises(IntegrityError):
            ShockType.objects.create(name="Conflict")

    def test_shock_type_default_values(self):
        """Test default values for shock type fields."""
        shock_type = ShockType.objects.create(name="Test Type")
        self.assertEqual(shock_type.icon, "📍")
        self.assertEqual(shock_type.color, "#6c757d")

    def test_shock_type_ordering(self):
        """Test shock type ordering by name."""
        ShockType.objects.create(name="Zebra")
        ShockType.objects.create(name="Alpha")

        shock_types = list(ShockType.objects.all())
        self.assertEqual(shock_types[0].name, "Alpha")
        self.assertEqual(shock_types[1].name, "Conflict")
        self.assertEqual(shock_types[2].name, "Zebra")


class AlertModelTest(TestCase):
    """Tests for Alert model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=cls.admin_level
        )

        cls.source = Source.objects.create(
            name="Test Source",
            description="Test data source",
            type="api",
            class_name="TestSource"
        )

        cls.shock_type = ShockType.objects.create(name="Conflict")

    def setUp(self):
        """Set up for each test."""
        now = timezone.now()
        self.alert = Alert.objects.create(
            title="Test Alert",
            text="This is a test alert",
            shock_type=self.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=now,
            valid_until=now + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )
        self.alert.locations.add(self.location)

    def test_alert_creation(self):
        """Test Alert creation."""
        self.assertEqual(self.alert.title, "Test Alert")
        self.assertEqual(self.alert.text, "This is a test alert")
        self.assertEqual(self.alert.shock_type, self.shock_type)
        self.assertEqual(self.alert.severity, 3)
        self.assertEqual(self.alert.shock_date, date.today())
        self.assertTrue(self.alert.go_no_go)
        self.assertIsNotNone(self.alert.created_at)
        self.assertIsNotNone(self.alert.updated_at)

    def test_alert_str(self):
        """Test Alert string representation."""
        expected = f"Test Alert ({date.today()})"
        self.assertEqual(str(self.alert), expected)

    def test_is_active_property(self):
        """Test is_active property."""
        # Current alert should be active
        self.assertTrue(self.alert.is_active)

        # Past alert should not be active
        past_alert = Alert.objects.create(
            title="Past Alert",
            text="This alert has expired",
            shock_type=self.shock_type,
            severity=2,
            shock_date=date.today() - timedelta(days=10),
            valid_from=timezone.now() - timedelta(days=10),
            valid_until=timezone.now() - timedelta(days=3),
            data_source=self.source,
            go_no_go=True,
        )
        self.assertFalse(past_alert.is_active)

        # Future alert should not be active yet
        future_alert = Alert.objects.create(
            title="Future Alert",
            text="This alert is not yet active",
            shock_type=self.shock_type,
            severity=1,
            shock_date=date.today() + timedelta(days=5),
            valid_from=timezone.now() + timedelta(days=5),
            valid_until=timezone.now() + timedelta(days=12),
            data_source=self.source,
            go_no_go=True,
        )
        self.assertFalse(future_alert.is_active)

    def test_severity_display_property(self):
        """Test severity_display property."""
        self.assertEqual(self.alert.severity_display, "High")

        # Test all severity levels
        severity_tests = [
            (1, "Low"),
            (2, "Moderate"),
            (3, "High"),
            (4, "Very High"),
            (5, "Critical")
        ]

        for severity, expected in severity_tests:
            alert = Alert.objects.create(
                title=f"Test Alert {severity}",
                text="Test",
                shock_type=self.shock_type,
                severity=severity,
                shock_date=date.today(),
                valid_from=timezone.now(),
                valid_until=timezone.now() + timedelta(days=7),
                data_source=self.source,
                go_no_go=True,
            )
            self.assertEqual(alert.severity_display, expected)

    def test_severity_validation(self):
        """Test severity field validation."""
        # Test invalid severity values
        with self.assertRaises(ValidationError):
            alert = Alert(
                title="Invalid Severity Alert",
                text="Test",
                shock_type=self.shock_type,
                severity=6,  # Invalid - too high
                shock_date=date.today(),
                valid_from=timezone.now(),
                valid_until=timezone.now() + timedelta(days=7),
                data_source=self.source,
            )
            alert.full_clean()

        with self.assertRaises(ValidationError):
            alert = Alert(
                title="Invalid Severity Alert",
                text="Test",
                shock_type=self.shock_type,
                severity=0,  # Invalid - too low
                shock_date=date.today(),
                valid_from=timezone.now(),
                valid_until=timezone.now() + timedelta(days=7),
                data_source=self.source,
            )
            alert.full_clean()

    def test_alert_ordering(self):
        """Test alert ordering."""
        # Create alerts with different dates
        yesterday_alert = Alert.objects.create(
            title="Yesterday Alert",
            text="Yesterday's alert",
            shock_type=self.shock_type,
            severity=2,
            shock_date=date.today() - timedelta(days=1),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )

        tomorrow_alert = Alert.objects.create(
            title="Tomorrow Alert",
            text="Tomorrow's alert",
            shock_type=self.shock_type,
            severity=4,
            shock_date=date.today() + timedelta(days=1),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )

        alerts = list(Alert.objects.all())
        # Should be ordered by shock_date desc, then created_at desc
        self.assertEqual(alerts[0], tomorrow_alert)
        self.assertEqual(alerts[1], self.alert)
        self.assertEqual(alerts[2], yesterday_alert)


class UserAlertModelTest(TestCase):
    """Tests for UserAlert model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=cls.admin_level
        )

        cls.source = Source.objects.create(
            name="Test Source",
            description="Test data source",
            type="api",
            class_name="TestSource"
        )

        cls.shock_type = ShockType.objects.create(name="Conflict")

        now = timezone.now()
        cls.alert = Alert.objects.create(
            title="Test Alert",
            text="This is a test alert",
            shock_type=cls.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=now,
            valid_until=now + timedelta(days=7),
            data_source=cls.source,
            go_no_go=True,
        )

    def setUp(self):
        """Set up for each test."""
        self.user_alert = UserAlert.objects.create(
            user=self.user,
            alert=self.alert,
            received_at=timezone.now(),
            read_at=timezone.now(),
            rating=4,
            rating_at=timezone.now(),
            bookmarked=True,
            comment="Great alert!"
        )

    def test_user_alert_creation(self):
        """Test UserAlert creation."""
        self.assertEqual(self.user_alert.user, self.user)
        self.assertEqual(self.user_alert.alert, self.alert)
        self.assertEqual(self.user_alert.rating, 4)
        self.assertTrue(self.user_alert.bookmarked)
        self.assertEqual(self.user_alert.comment, "Great alert!")
        self.assertIsNotNone(self.user_alert.received_at)
        self.assertIsNotNone(self.user_alert.read_at)
        self.assertIsNotNone(self.user_alert.rating_at)

    def test_user_alert_str(self):
        """Test UserAlert string representation."""
        expected = f"{self.user.username} - {self.alert.title}"
        self.assertEqual(str(self.user_alert), expected)

    def test_is_read_property(self):
        """Test is_read property."""
        self.assertTrue(self.user_alert.is_read)

        # Test unread alert with different user
        unread_user = User.objects.create_user(username="unreaduser", email="unread@example.com")
        unread_alert = UserAlert.objects.create(
            user=unread_user,
            alert=self.alert,
            received_at=timezone.now()
            # No read_at set
        )
        self.assertFalse(unread_alert.is_read)

    def test_is_rated_property(self):
        """Test is_rated property."""
        self.assertTrue(self.user_alert.is_rated)

        # Test unrated alert with different user
        unrated_user = User.objects.create_user(username="unrateduser", email="unrated@example.com")
        unrated_alert = UserAlert.objects.create(
            user=unrated_user,
            alert=self.alert,
            received_at=timezone.now()
            # No rating set
        )
        self.assertFalse(unrated_alert.is_rated)

    def test_is_flagged_property(self):
        """Test is_flagged property."""
        # Initially not flagged
        self.assertFalse(self.user_alert.is_flagged)

        # Test false flag
        self.user_alert.flag_false = True
        self.user_alert.save()
        self.assertTrue(self.user_alert.is_flagged)

        # Test incomplete flag
        self.user_alert.flag_false = False
        self.user_alert.flag_incomplete = True
        self.user_alert.save()
        self.assertTrue(self.user_alert.is_flagged)

        # Test both flags
        self.user_alert.flag_false = True
        self.user_alert.save()
        self.assertTrue(self.user_alert.is_flagged)

    def test_unique_together_constraint(self):
        """Test unique together constraint for user and alert."""
        with self.assertRaises(IntegrityError):
            UserAlert.objects.create(
                user=self.user,
                alert=self.alert  # Same user-alert combination
            )

    def test_rating_validation(self):
        """Test rating field validation."""
        # Test invalid rating values
        with self.assertRaises(ValidationError):
            user_alert = UserAlert(
                user=self.user,
                alert=self.alert,
                rating=6  # Invalid - too high
            )
            user_alert.full_clean()

        with self.assertRaises(ValidationError):
            user_alert = UserAlert(
                user=self.user,
                alert=self.alert,
                rating=0  # Invalid - too low
            )
            user_alert.full_clean()

    def test_user_alert_ordering(self):
        """Test UserAlert ordering by updated_at."""
        # Create another user alert
        user2 = User.objects.create_user(username="testuser2", email="test2@example.com")

        older_alert = UserAlert.objects.create(
            user=user2,
            alert=self.alert,
            received_at=timezone.now() - timedelta(hours=1)
        )

        # Update the older alert to change updated_at
        older_alert.comment = "Updated comment"
        older_alert.save()

        alerts = list(UserAlert.objects.all())
        # Should be ordered by updated_at desc
        self.assertEqual(alerts[0], older_alert)  # Most recently updated
        self.assertEqual(alerts[1], self.user_alert)


class AlertModelPropertyTest(TestCase):
    """Tests for Alert model properties and aggregated data."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user1 = User.objects.create_user(username="user1", email="user1@example.com")
        cls.user2 = User.objects.create_user(username="user2", email="user2@example.com")
        cls.user3 = User.objects.create_user(username="user3", email="user3@example.com")

        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=cls.admin_level
        )

        cls.source = Source.objects.create(
            name="Test Source",
            description="Test data source",
            type="api",
            class_name="TestSource"
        )

        cls.shock_type = ShockType.objects.create(name="Conflict")

        now = timezone.now()
        cls.alert = Alert.objects.create(
            title="Test Alert with Ratings",
            text="This alert will have multiple ratings",
            shock_type=cls.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=now,
            valid_until=now + timedelta(days=7),
            data_source=cls.source,
            go_no_go=True,
        )

    def test_average_rating_property(self):
        """Test average_rating property calculation."""
        # No ratings initially
        self.assertIsNone(self.alert.average_rating)

        # Add ratings
        UserAlert.objects.create(user=self.user1, alert=self.alert, rating=5)
        UserAlert.objects.create(user=self.user2, alert=self.alert, rating=3)
        UserAlert.objects.create(user=self.user3, alert=self.alert, rating=4)

        # Should calculate average: (5 + 3 + 4) / 3 = 4.0
        self.assertEqual(self.alert.average_rating, 4.0)

        # Add a fourth user without rating (to verify non-rated users don't affect average)
        user4 = User.objects.create_user(username="user4", email="user4@example.com")
        UserAlert.objects.create(user=user4, alert=self.alert, bookmarked=True)
        # Average should remain the same (only rated alerts counted)
        self.assertEqual(self.alert.average_rating, 4.0)

    def test_rating_count_property(self):
        """Test rating_count property."""
        # Create a separate alert for this test to avoid conflicts
        test_alert = Alert.objects.create(
            title="Rating Count Test Alert",
            text="Alert for testing rating count",
            shock_type=self.shock_type,
            severity=2,
            shock_date=timezone.now().date(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=5),
            data_source=self.source,
            go_no_go=True,
        )

        # No ratings initially
        self.assertEqual(test_alert.rating_count, 0)

        # Add ratings
        UserAlert.objects.create(user=self.user1, alert=test_alert, rating=5)
        UserAlert.objects.create(user=self.user2, alert=test_alert, rating=3)

        self.assertEqual(test_alert.rating_count, 2)

        # Add user interaction without rating
        UserAlert.objects.create(user=self.user3, alert=test_alert, bookmarked=True)
        # Count should remain 2
        self.assertEqual(test_alert.rating_count, 2)

    def test_flag_properties(self):
        """Test flag-related properties."""
        # Create a separate alert for this test to avoid conflicts
        test_alert = Alert.objects.create(
            title="Flag Test Alert",
            text="Alert for testing flags",
            shock_type=self.shock_type,
            severity=2,
            shock_date=timezone.now().date(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=5),
            data_source=self.source,
            go_no_go=True,
        )

        # Initially no flags
        self.assertFalse(test_alert.is_flagged_false)
        self.assertFalse(test_alert.is_flagged_incomplete)
        self.assertEqual(test_alert.false_flag_count, 0)
        self.assertEqual(test_alert.incomplete_flag_count, 0)

        # Add false flags
        UserAlert.objects.create(user=self.user1, alert=test_alert, flag_false=True)
        UserAlert.objects.create(user=self.user2, alert=test_alert, flag_false=True)

        self.assertTrue(test_alert.is_flagged_false)
        self.assertEqual(test_alert.false_flag_count, 2)
        self.assertFalse(test_alert.is_flagged_incomplete)
        self.assertEqual(test_alert.incomplete_flag_count, 0)

        # Add incomplete flag
        UserAlert.objects.create(user=self.user3, alert=test_alert, flag_incomplete=True)

        self.assertTrue(test_alert.is_flagged_incomplete)
        self.assertEqual(test_alert.incomplete_flag_count, 1)

    def test_get_all_comments_method(self):
        """Test get_all_comments method."""
        # Create a separate alert for this test to avoid conflicts
        test_alert = Alert.objects.create(
            title="Comments Test Alert",
            text="Alert for testing comments",
            shock_type=self.shock_type,
            severity=2,
            shock_date=timezone.now().date(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=5),
            data_source=self.source,
            go_no_go=True,
        )

        # No comments initially
        comments = test_alert.get_all_comments()
        self.assertEqual(comments.count(), 0)

        # Add comments
        UserAlert.objects.create(
            user=self.user1,
            alert=test_alert,
            comment="Great alert!",
            created_at=timezone.now() - timedelta(minutes=10)
        )
        UserAlert.objects.create(
            user=self.user2,
            alert=test_alert,
            comment="Very informative",
            created_at=timezone.now() - timedelta(minutes=5)
        )

        # Add user alert without comment
        UserAlert.objects.create(user=self.user3, alert=test_alert, rating=4)

        # Add user alert with empty comment
        UserAlert.objects.create(
            user=User.objects.create_user(username="user4", email="user4@example.com"),
            alert=test_alert,
            comment=""
        )

        comments = test_alert.get_all_comments()
        self.assertEqual(comments.count(), 2)

        # Should be ordered by created_at desc (most recent first)
        comment_list = list(comments)
        self.assertEqual(comment_list[0].comment, "Very informative")
        self.assertEqual(comment_list[1].comment, "Great alert!")

        # Should include user data (select_related)
        self.assertEqual(comment_list[0].user, self.user2)


class SubscriptionModelTest(TestCase):
    """Tests for Subscription model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=cls.admin_level
        )

        cls.shock_type = ShockType.objects.create(name="Conflict")

    def setUp(self):
        """Set up for each test."""
        self.subscription = Subscription.objects.create(
            user=self.user,
            frequency="daily",
            method="email",
            active=True
        )
        self.subscription.locations.add(self.location)
        self.subscription.shock_types.add(self.shock_type)

    def test_subscription_creation(self):
        """Test Subscription creation."""
        self.assertEqual(self.subscription.user, self.user)
        self.assertEqual(self.subscription.frequency, "daily")
        self.assertEqual(self.subscription.method, "email")
        self.assertTrue(self.subscription.active)
        self.assertIsNotNone(self.subscription.created_at)
        self.assertIsNotNone(self.subscription.updated_at)

    def test_subscription_str(self):
        """Test Subscription string representation."""
        expected = f"{self.user.username} - email (daily)"
        self.assertEqual(str(self.subscription), expected)

    def test_subscription_default_values(self):
        """Test default values for subscription fields."""
        subscription = Subscription.objects.create(user=self.user)
        self.assertEqual(subscription.method, "email")
        self.assertEqual(subscription.frequency, "immediate")
        self.assertTrue(subscription.active)

    def test_subscription_ordering(self):
        """Test subscription ordering by created_at."""
        # Create another subscription later
        newer_subscription = Subscription.objects.create(
            user=self.user,
            frequency="weekly"
        )

        subscriptions = list(Subscription.objects.all())
        # Should be ordered by created_at desc
        self.assertEqual(subscriptions[0], newer_subscription)
        self.assertEqual(subscriptions[1], self.subscription)

    def test_subscription_many_to_many_relationships(self):
        """Test many-to-many relationships."""
        # Test locations
        self.assertEqual(self.subscription.locations.count(), 1)
        self.assertIn(self.location, self.subscription.locations.all())

        # Test shock types
        self.assertEqual(self.subscription.shock_types.count(), 1)
        self.assertIn(self.shock_type, self.subscription.shock_types.all())

        # Add more relations
        location2 = Location.objects.create(
            name="Port Sudan",
            geo_id="SD002",
            admin_level=self.admin_level
        )
        shock_type2 = ShockType.objects.create(name="Natural Disaster")

        self.subscription.locations.add(location2)
        self.subscription.shock_types.add(shock_type2)

        self.assertEqual(self.subscription.locations.count(), 2)
        self.assertEqual(self.subscription.shock_types.count(), 2)


class EmailTemplateModelTest(TestCase):
    """Tests for EmailTemplate model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

        self.template = EmailTemplate.objects.create(
            name="individual_alert",
            description="Individual alert notification template",
            subject="[EWAS Alert] {{alert.title}}",
            html_header="<h2>Alert Notification</h2>",
            html_footer="<p>Thank you for using EWAS.</p>",
            text_header="ALERT NOTIFICATION\n==================",
            text_footer="\nThank you for using EWAS.",
            active=True
        )

        # Create a mock alert for template testing
        admin_level = AdmLevel.objects.create(code="1", name="State Level")
        location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=admin_level
        )
        source = Source.objects.create(
            name="Test Source",
            description="Test data source",
            type="api",
            class_name="TestSource"
        )
        shock_type = ShockType.objects.create(name="Conflict")

        now = timezone.now()
        self.alert = Alert.objects.create(
            title="Test Alert",
            text="This is a test alert",
            shock_type=shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=now,
            valid_until=now + timedelta(days=7),
            data_source=source,
            go_no_go=True,
        )

    def test_email_template_creation(self):
        """Test EmailTemplate creation."""
        self.assertEqual(self.template.name, "individual_alert")
        self.assertEqual(self.template.description, "Individual alert notification template")
        self.assertEqual(self.template.subject, "[EWAS Alert] {{alert.title}}")
        self.assertTrue(self.template.active)
        self.assertIsNotNone(self.template.created_at)
        self.assertIsNotNone(self.template.updated_at)

    def test_email_template_str(self):
        """Test EmailTemplate string representation."""
        expected = "Individual Alert - [EWAS Alert] {{alert.title}}"
        self.assertEqual(str(self.template), expected)

    def test_email_template_str_truncation(self):
        """Test EmailTemplate string representation truncation."""
        long_subject = "This is a very long subject line that should be truncated at fifty characters for display"
        template = EmailTemplate.objects.create(
            name="daily_digest",
            description="Daily digest template",
            subject=long_subject,
            html_header="<h1>Daily Digest</h1>",
            text_header="Daily Digest",
            active=True
        )

        # Should truncate at 50 characters
        expected = f"Daily Digest - {long_subject[:50]}"
        self.assertEqual(str(template), expected)

    def test_unique_name_constraint(self):
        """Test that template names must be unique."""
        with self.assertRaises(IntegrityError):
            EmailTemplate.objects.create(
                name="individual_alert",  # Same name
                description="Duplicate template",
                subject="Test",
                html_header="Test",
                text_header="Test"
            )

    def test_render_html_method(self):
        """Test HTML template rendering."""
        context = {
            'user': self.user,
            'alert': self.alert,
            'unsubscribe_url': 'http://example.com/unsubscribe'
        }

        html_content = self.template.render_html(context)

        # Check that header, alert content, and footer are included
        self.assertIn("<h2>Alert Notification</h2>", html_content)
        self.assertIn("Test Alert", html_content)
        self.assertIn("This is a test alert", html_content)
        self.assertIn("<p>Thank you for using EWAS.</p>", html_content)

    def test_render_text_method(self):
        """Test text template rendering."""
        context = {
            'user': self.user,
            'alert': self.alert,
            'unsubscribe_url': 'http://example.com/unsubscribe'
        }

        text_content = self.template.render_text(context)

        # Check that header, alert content, and footer are included
        self.assertIn("ALERT NOTIFICATION", text_content)
        self.assertIn("Test Alert", text_content)
        self.assertIn("This is a test alert", text_content)
        self.assertIn("Thank you for using EWAS.", text_content)

    def test_get_subject_method(self):
        """Test subject rendering with template variables."""
        context = {
            'user': self.user,
            'alert': self.alert
        }

        subject = self.template.get_subject(context)
        expected = f"[EWAS Alert] {self.alert.title}"
        self.assertEqual(subject, expected)

    def test_render_with_wrapper_template(self):
        """Test rendering with wrapper templates."""
        self.template.html_wrapper = """
        <html>
        <head><title>{{alert.title}}</title></head>
        <body>
            <h1>EWAS System</h1>
            {{content}}
            <footer>EWAS Footer</footer>
        </body>
        </html>
        """
        self.template.save()

        context = {'user': self.user, 'alert': self.alert}
        html_content = self.template.render_html(context)

        self.assertIn(f"<title>{self.alert.title}</title>", html_content)
        self.assertIn("<h1>EWAS System</h1>", html_content)
        self.assertIn("EWAS Footer", html_content)

    def test_template_ordering(self):
        """Test template ordering by name."""
        EmailTemplate.objects.create(
            name="daily_digest",
            description="Daily digest",
            subject="Daily Digest",
            html_header="<h1>Daily</h1>",
            text_header="Daily",
            active=True
        )

        templates = list(EmailTemplate.objects.all())
        # Should be ordered alphabetically by name
        self.assertEqual(templates[0].name, "daily_digest")
        self.assertEqual(templates[1].name, "individual_alert")

    def test_template_verbose_names(self):
        """Test model verbose names."""
        self.assertEqual(EmailTemplate._meta.verbose_name, "Email Template")
        self.assertEqual(EmailTemplate._meta.verbose_name_plural, "Email Templates")
"""Tests for alerts app admin interface."""

from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from alerts.admin import AlertAdmin
from alerts.models import Alert, ShockType
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class AdminBasicTest(TestCase):
    """Essential tests for admin functionality."""

    def setUp(self):
        """Set up test data."""
        self.site = AdminSite()

        # Create admin user
        self.admin_user = User.objects.create_superuser(
            username="admin_test",
            email="admin@test.com",
            password="admin123"
        )

        # Create test data
        self.shock_type = ShockType.objects.create(
            name="Conflict",
            icon="fa-warning",
            color="#ff0000"
        )

        # Create data source
        self.data_source = Source.objects.create(
            name="Test Source",
            description="Test data source for admin tests",
            is_active=True
        )

        country_level = AdmLevel.objects.create(code="0", name="Country")
        self.location = Location.objects.create(
            name="Test Location",
            admin_level=country_level,
            geo_id="SD"
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
        self.alert.locations.add(self.location)

    def test_admin_access_requires_superuser(self):
        """Test that admin access requires superuser permissions."""
        # Test with superuser
        self.client.login(username="admin_test", password="admin123")
        response = self.client.get("/admin/alerts/alert/")
        self.assertEqual(response.status_code, 200)

    def test_alert_admin_custom_actions(self):
        """Test custom admin actions for alerts."""
        admin = AlertAdmin(Alert, self.site)

        # Verify custom actions exist
        self.assertIn("approve_alerts", admin.actions)
        self.assertIn("reject_alerts", admin.actions)

    def test_alert_approval_via_admin(self):
        """Test alert approval through admin action."""
        # Create unapproved alert
        unapproved_alert = Alert.objects.create(
            title="Unapproved Alert",
            text="This alert needs approval",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=2,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=5),
            go_no_go=False
        )

        self.client.login(username="admin_test", password="admin123")
        response = self.client.post("/admin/alerts/alert/", {
            "action": "approve_alerts",
            "_selected_action": [unapproved_alert.id]
        })

        # Verify action was successful
        self.assertIn(response.status_code, [200, 302])
        unapproved_alert.refresh_from_db()
        self.assertTrue(unapproved_alert.go_no_go)

    def test_shock_type_admin_functionality(self):
        """Test basic ShockType admin functionality."""
        self.client.login(username="admin_test", password="admin123")
        response = self.client.get("/admin/alerts/shocktype/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conflict")

    def test_subscription_admin_functionality(self):
        """Test basic Subscription admin functionality."""
        self.client.login(username="admin_test", password="admin123")
        response = self.client.get("/admin/alerts/subscription/")
        self.assertEqual(response.status_code, 200)
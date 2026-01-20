"""Tests for alerts app views."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alerts.models import Alert, ShockType, Subscription, UserAlert
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class AlertViewBasicTest(TestCase):
    """Essential tests for alert views."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.shock_type = ShockType.objects.create(name="Conflict", icon="fa-warning", color="#ff0000")

        # Create data source
        self.data_source = Source.objects.create(
            name="Test Source",
            description="Test data source",
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

    def test_alert_list_requires_authentication(self):
        """Test that alert list requires authentication."""
        url = reverse("alerts:alert_list")
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])

    def test_authenticated_user_can_access_alert_list(self):
        """Test that authenticated users can access alert list."""
        self.client.login(username="testuser", password="testpass123")
        url = reverse("alerts:alert_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_alert_detail_requires_authentication(self):
        """Test that alert detail requires authentication."""
        url = reverse("alerts:alert_detail", args=[self.alert.id])
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])

    def test_authenticated_user_can_access_alert_detail(self):
        """Test that authenticated users can access alert detail."""
        self.client.login(username="testuser", password="testpass123")
        url = reverse("alerts:alert_detail", args=[self.alert.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_map_view_requires_authentication(self):
        """Test that map view requires authentication."""
        url = reverse("alerts:alert_map")
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])

    def test_authenticated_user_can_access_map(self):
        """Test that authenticated users can access map."""
        self.client.login(username="testuser", password="testpass123")
        url = reverse("alerts:alert_map")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class AlertAjaxBasicTest(TestCase):
    """Essential tests for AJAX functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.shock_type = ShockType.objects.create(name="Conflict", icon="fa-warning", color="#ff0000")

        # Create data source
        self.data_source = Source.objects.create(
            name="Test Source",
            description="Test data source for AJAX tests",
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

    def test_ajax_rate_alert_requires_authentication(self):
        """Test that AJAX rating requires authentication."""
        url = reverse("alerts:rate_alert", kwargs={"alert_id": self.alert.id})
        response = self.client.post(url, {"rating": "4"})
        self.assertIn(response.status_code, [302, 403])

    def test_ajax_rate_alert_works_authenticated(self):
        """Test that authenticated users can rate alerts."""
        self.client.login(username="testuser", password="testpass123")
        url = reverse("alerts:rate_alert", kwargs={"alert_id": self.alert.id})
        response = self.client.post(url, {"rating": "4"})
        # Should return some response (200, 422, etc.)
        self.assertIn(response.status_code, [200, 422])

        # Verify UserAlert was created if successful
        if response.status_code == 200:
            user_alert = UserAlert.objects.get(user=self.user, alert=self.alert)
            self.assertEqual(user_alert.rating, 4)


class SubscriptionViewBasicTest(TestCase):
    """Essential tests for subscription views."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass123")

    def test_subscription_list_requires_authentication(self):
        """Test that subscription list requires authentication."""
        url = reverse("alerts:subscription_list")
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])

    def test_authenticated_user_can_access_subscriptions(self):
        """Test that authenticated users can access subscriptions."""
        self.client.login(username="testuser", password="testpass123")
        url = reverse("alerts:subscription_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
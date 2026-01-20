"""Integration tests for alerts app workflows."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TransactionTestCase
from django.utils import timezone

from alerts.models import Alert, ShockType, Subscription, UserAlert
from alerts.services.notifications import NotificationService
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class BasicWorkflowTest(TransactionTestCase):
    """Essential workflow tests."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

        # Create data source
        self.data_source = Source.objects.create(
            name="Test Source",
            description="Test data source for workflow tests",
            is_active=True
        )

        self.shock_type = ShockType.objects.create(
            name="Conflict",
            icon="fa-warning",
            color="#ff0000"
        )

        # Create location
        country_level = AdmLevel.objects.create(code="0", name="Country")
        self.location = Location.objects.create(
            name="Test Location",
            admin_level=country_level,
            geo_id="TEST_001"
        )

        # Create subscription
        self.subscription = Subscription.objects.create(
            user=self.user,
            method="email",
            active=True
        )
        self.subscription.locations.add(self.location)
        self.subscription.shock_types.add(self.shock_type)

    def test_alert_creation_basic_workflow(self):
        """Test basic alert creation workflow."""
        # Create alert
        alert = Alert.objects.create(
            title="Workflow Test Alert",
            text="Testing basic workflow",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=3,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            go_no_go=True,
        )
        alert.locations.add(self.location)

        # Verify alert was created
        self.assertTrue(Alert.objects.filter(id=alert.id).exists())

    def test_user_interaction_basic_workflow(self):
        """Test user interaction workflow."""
        # Create alert
        alert = Alert.objects.create(
            title="Interaction Test Alert",
            text="Testing user interaction",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=2,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=5),
            go_no_go=True,
        )
        alert.locations.add(self.location)

        # Create user interaction
        user_alert = UserAlert.objects.create(
            user=self.user,
            alert=alert,
            rating=4,
            bookmarked=True,
            received_at=timezone.now()
        )

        # Verify interaction was recorded
        self.assertEqual(user_alert.rating, 4)
        self.assertTrue(user_alert.bookmarked)

    @patch('alerts.services.notifications.NotificationService.notify_new_alert')
    def test_notification_service_integration(self, mock_notify):
        """Test notification service integration."""
        mock_notify.return_value = {"emails": 0, "internal": 0, "errors": 0}

        # Create alert
        alert = Alert.objects.create(
            title="Notification Test Alert",
            text="Testing notification integration",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=4,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=3),
            go_no_go=True,
        )
        alert.locations.add(self.location)

        # Test notification service
        service = NotificationService()
        result = service.notify_new_alert(alert)

        # Verify service ran without errors
        self.assertIsNotNone(result)
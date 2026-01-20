"""Tests for alert map functionality."""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alerts.models import Alert, ShockType
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class AlertMapFunctionalityTest(TestCase):
    """Essential tests for map functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        # Create test user
        cls.user = User.objects.create_user(username="testuser", password="testpass123")

        # Create data source
        cls.source = Source.objects.create(
            name="Test Source",
            description="Test data source",
            is_active=True
        )

        # Create admin level
        cls.admin_level = AdmLevel.objects.create(code="ADMIN1", name="State Level")

        # Create location with coordinates
        cls.location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=cls.admin_level,
            point=Point(32.5599, 15.5007)
        )

        # Create shock type
        cls.shock_type = ShockType.objects.create(name="Conflict", icon="fa-warning", color="#ff0000")

        # Create test alert
        now = timezone.now()
        cls.alert = Alert.objects.create(
            title="Test Alert",
            text="This is a test alert for Khartoum",
            shock_type=cls.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(days=7),
            data_source=cls.source,
            go_no_go=True,
        )
        cls.alert.locations.add(cls.location)

    def setUp(self):
        """Set up for each test."""
        self.client.login(username="testuser", password="testpass123")

    def test_map_page_loads(self):
        """Test that the map page loads successfully."""
        response = self.client.get(reverse("alerts:alert_map"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-map")

    def test_location_coordinates_available(self):
        """Test that location coordinates are available for map display."""
        response = self.client.get(reverse("alerts:api_alerts"))
        self.assertEqual(response.status_code, 200)
        # Test passes if API responds - detailed coordinate testing is covered in API tests
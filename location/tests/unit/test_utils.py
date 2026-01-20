"""Unit tests for location utilities (non-matching related)."""

from django.test import TestCase

from location.models import AdmLevel, Location
from location.utils import LocationMatcher


class LocationUtilityTests(TestCase):
    """Tests for LocationMatcher utility methods not covered in test_locationmatching."""

    def setUp(self):
        """Set up test data."""
        self.matcher = LocationMatcher()

        # Create admin levels
        self.admin0 = AdmLevel.objects.create(code="0", name="Country")
        self.admin1 = AdmLevel.objects.create(code="1", name="State")

        # Create locations
        self.country = Location.objects.create(geo_id="SD", name="Sudan", admin_level=self.admin0)

        self.khartoum = Location.objects.create(geo_id="SD_001", name="Khartoum", admin_level=self.admin1, parent=self.country)

        self.kassala = Location.objects.create(geo_id="SD_002", name="Kassala", admin_level=self.admin1, parent=self.country)

    def tearDown(self):
        """Clean up after tests."""
        self.matcher.clear_cache()

    def test_get_all_locations_for_manual_review(self):
        """Test getting locations for manual gazetteer review."""
        locations = self.matcher.get_all_locations_for_manual_review(limit=5)

        self.assertTrue(len(locations) > 0)
        self.assertIn(self.khartoum, locations)
        self.assertIn(self.kassala, locations)
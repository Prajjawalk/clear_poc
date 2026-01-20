"""Unit tests for location models."""

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.exceptions import ValidationError
from django.test import TestCase

from location.models import AdmLevel, Gazetteer, Location


class AdmLevelModelTests(TestCase):
    """Tests for AdmLevel model."""

    def setUp(self):
        """Set up test data."""
        self.admin0 = AdmLevel.objects.create(code="0", name="Country", name_en="Country", name_ar="دولة")
        self.admin1 = AdmLevel.objects.create(code="1", name="State", name_en="State", name_ar="ولاية")

    def test_adm_level_creation(self):
        """Test AdmLevel model creation."""
        self.assertEqual(self.admin0.code, "0")
        self.assertEqual(self.admin0.name, "Country")
        self.assertEqual(str(self.admin0), "Admin Level 0: Country")

    def test_adm_level_ordering(self):
        """Test AdmLevel ordering by code."""
        levels = list(AdmLevel.objects.all())
        self.assertEqual(levels[0].code, "0")
        self.assertEqual(levels[1].code, "1")

    def test_unique_code_constraint(self):
        """Test that AdmLevel codes must be unique."""
        with self.assertRaises(Exception):
            AdmLevel.objects.create(code="0", name="Duplicate")


class LocationModelTests(TestCase):
    """Tests for Location model."""

    def setUp(self):
        """Set up test data."""
        self.admin0 = AdmLevel.objects.create(code="0", name="Country")
        self.admin1 = AdmLevel.objects.create(code="1", name="State")
        self.admin2 = AdmLevel.objects.create(code="2", name="District")

        # Create hierarchical locations
        self.country = Location.objects.create(
            geo_id="SD", name="Sudan", name_en="Sudan", name_ar="السودان", admin_level=self.admin0, point=Point(30.0, 15.0), comment="Republic of Sudan"
        )

        self.state = Location.objects.create(
            geo_id="SD_001", name="Khartoum", name_en="Khartoum", name_ar="الخرطوم", admin_level=self.admin1, parent=self.country, point=Point(32.5, 15.6)
        )

        self.district = Location.objects.create(geo_id="SD_001_001", name="Khartoum Central", admin_level=self.admin2, parent=self.state, point=Point(32.5, 15.6))

    def test_location_creation(self):
        """Test Location model creation."""
        self.assertEqual(self.country.geo_id, "SD")
        self.assertEqual(self.country.name, "Sudan")
        self.assertEqual(str(self.country), "SD: Sudan")
        self.assertIsNone(self.country.parent)

    def test_location_hierarchy(self):
        """Test hierarchical relationships."""
        self.assertEqual(self.state.parent, self.country)
        self.assertEqual(self.district.parent, self.state)
        self.assertIn(self.state, self.country.children.all())
        self.assertIn(self.district, self.state.children.all())

    def test_geo_id_validation(self):
        """Test geo_id format validation."""
        # Valid formats should work
        valid_ids = ["US", "US_001", "US_001_002", "US_123_456"]
        for geo_id in valid_ids:
            try:
                location = Location(geo_id=geo_id, name="Test", name_en="Test", name_ar="اختبار", admin_level=self.admin0)
                location.full_clean()
            except ValidationError as e:
                self.fail(f"Valid geo_id {geo_id} failed validation: {e}")

        # Invalid formats should fail
        invalid_ids = ["us", "US_", "US__001", "US_abc", "A_001", "US_12", "US_001_ab"]
        for geo_id in invalid_ids:
            with self.assertRaises(ValidationError):
                location = Location(geo_id=geo_id, name="Test", name_en="Test", name_ar="اختبار", admin_level=self.admin0)
                location.full_clean()

    def test_get_full_hierarchy(self):
        """Test get_full_hierarchy method."""
        hierarchy = self.district.get_full_hierarchy()
        expected = [self.country, self.state, self.district]
        self.assertEqual(hierarchy, expected)

        # Test single level
        country_hierarchy = self.country.get_full_hierarchy()
        self.assertEqual(country_hierarchy, [self.country])

    def test_get_descendants(self):
        """Test get_descendants method."""
        descendants = self.country.get_descendants()
        self.assertIn(self.state, descendants)
        self.assertIn(self.district, descendants)

        state_descendants = self.state.get_descendants()
        self.assertIn(self.district, state_descendants)
        self.assertNotIn(self.country, state_descendants)

    def test_get_children_at_level(self):
        """Test get_children_at_level method."""
        admin1_children = self.country.get_children_at_level("1")
        self.assertIn(self.state, admin1_children)

        admin2_children = self.country.get_children_at_level("2")
        self.assertIn(self.district, admin2_children)

    def test_location_with_boundaries(self):
        """Test location with geographic boundaries."""
        # Create a polygon boundary
        boundary_coords = [(31.0, 14.0), (33.0, 14.0), (33.0, 16.0), (31.0, 16.0), (31.0, 14.0)]
        polygon = Polygon(boundary_coords)
        multi_polygon = MultiPolygon([polygon])

        location_with_boundary = Location.objects.create(geo_id="SD_999", name="Test Area", admin_level=self.admin1, parent=self.country, boundary=multi_polygon)

        self.assertIsNotNone(location_with_boundary.boundary)
        self.assertTrue(location_with_boundary.boundary.contains(Point(32.0, 15.0)))


class GazetteerModelTests(TestCase):
    """Tests for Gazetteer model."""

    def setUp(self):
        """Set up test data."""
        self.admin1 = AdmLevel.objects.create(code="1", name="State")
        self.location = Location.objects.create(geo_id="SD_001", name="Khartoum", admin_level=self.admin1)

    def test_gazetteer_creation(self):
        """Test Gazetteer model creation."""
        entry = Gazetteer.objects.create(location=self.location, source="ACLED", name="Khartum", code="KHA")

        self.assertEqual(entry.location, self.location)
        self.assertEqual(entry.source, "ACLED")
        self.assertEqual(entry.name, "Khartum")
        self.assertEqual(str(entry), "Khartum (KHA) [ACLED] -> SD_001")

    def test_gazetteer_without_code(self):
        """Test Gazetteer entry without code."""
        entry = Gazetteer.objects.create(location=self.location, source="UNHCR", name="Al Khartum")

        self.assertEqual(str(entry), "Al Khartum [UNHCR] -> SD_001")

    def test_unique_constraints(self):
        """Test unique constraints on Gazetteer."""
        # Create initial entry
        Gazetteer.objects.create(location=self.location, source="ACLED", name="Khartoum", code="KHA")

        # Same location, source, name should fail
        with self.assertRaises(Exception):
            Gazetteer.objects.create(location=self.location, source="ACLED", name="Khartoum")

        # Same location, source, code should fail
        with self.assertRaises(Exception):
            Gazetteer.objects.create(location=self.location, source="ACLED", name="Different Name", code="KHA")
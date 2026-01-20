"""Unit tests for enhanced location matching functionality."""

import logging
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from location.models import AdmLevel, Gazetteer, Location
from location.utils import LocationMatcher

# Suppress debug logging during tests
logging.disable(logging.DEBUG)


class LocationMatchingTestCase(TestCase):
    """Test cases for database-driven location matching improvements."""

    def setUp(self):
        """Set up test data for location matching tests."""
        # Create administrative levels
        self.country_level = AdmLevel.objects.create(name="Country", code="0")
        self.state_level = AdmLevel.objects.create(name="State", code="1")
        self.locality_level = AdmLevel.objects.create(name="Locality", code="2")

        # Create country
        self.sudan = Location.objects.create(
            name="Sudan",
            admin_level=self.country_level,
            geo_id="SDN",
        )

        # Create states
        self.north_darfur = Location.objects.create(
            name="North Darfur",
            admin_level=self.state_level,
            parent=self.sudan,
            geo_id="SDN_ND",
        )

        self.south_darfur = Location.objects.create(
            name="South Darfur",
            admin_level=self.state_level,
            parent=self.sudan,
            geo_id="SDN_SD",
        )

        self.khartoum = Location.objects.create(
            name="Khartoum",
            admin_level=self.state_level,
            parent=self.sudan,
            geo_id="SDN_KH",
        )

        # Create locality
        self.al_fasher = Location.objects.create(
            name="Al Fasher",
            admin_level=self.locality_level,
            parent=self.north_darfur,
            geo_id="SDN_ND_AF",
        )

        # Create gazetteer entries with various sources
        Gazetteer.objects.create(
            location=self.south_darfur,
            name="South Darfur",
            source="UNOCHA",
        )

        Gazetteer.objects.create(
            location=self.khartoum,
            name="Khartoum State",
            source="IDMC",
        )

        Gazetteer.objects.create(
            location=self.al_fasher,
            name="Al Fasher City",
            source="OSM",
        )

        # Create unmatched location entries to test country suffix detection
        try:
            from location.models import UnmatchedLocation

            UnmatchedLocation.objects.create(
                name="South Darfur State, Sudan",
                source="IDMC IDU",
                occurrence_count=200,
                status="pending",
            )
            UnmatchedLocation.objects.create(
                name="Khartoum State, Sudan",
                source="IDMC IDU",
                occurrence_count=150,
                status="pending",
            )
            UnmatchedLocation.objects.create(
                name="Al Fasher, North Darfur State, Sudan",
                source="IDMC IDU",
                occurrence_count=100,
                status="pending",
            )
        except ImportError:
            # UnmatchedLocation model might not be available in all deployments
            pass

        # Initialize matcher
        self.matcher = LocationMatcher()

    def tearDown(self):
        """Clean up after tests."""
        self.matcher.clear_cache()

    def test_suffix_cache_loading_from_admin_levels(self):
        """Test that admin level suffixes are correctly extracted from database."""
        self.matcher._load_suffix_cache()

        admin_suffixes = self.matcher._suffix_cache.get("admin", set())

        # Should contain suffixes from our AdmLevel objects
        self.assertIn(" state", admin_suffixes)
        self.assertIn(" states", admin_suffixes)  # Plural form
        self.assertIn(" locality", admin_suffixes)
        self.assertIn(" localities", admin_suffixes)  # Plural form

    def test_country_suffix_detection_from_unmatched_locations(self):
        """Test that country suffixes are detected from unmatched location patterns."""
        self.matcher._load_suffix_cache()

        country_suffixes = self.matcher._suffix_cache.get("country", set())

        # Should detect ", sudan" from unmatched location patterns
        self.assertIn(", sudan", country_suffixes)

    def test_geographic_suffix_extraction_from_existing_data(self):
        """Test that geographic suffixes are extracted from location and gazetteer names."""
        self.matcher._load_suffix_cache()

        geographic_suffixes = self.matcher._suffix_cache.get("geographic", set())

        # Should extract "city" from "Al Fasher City" in gazetteer
        self.assertIn(" city", geographic_suffixes)

    def test_prefix_cache_loading(self):
        """Test that prefixes are correctly extracted from existing location data."""
        self.matcher._load_suffix_cache()  # This also loads prefixes

        # Should detect "al " prefix from "Al Fasher"
        self.assertIn("al ", self.matcher._prefix_cache)

    def test_name_variations_generation(self):
        """Test that name variations are correctly generated using database-derived data."""
        # Test with state suffix
        variations = self.matcher._generate_name_variations("South Darfur State, Sudan")

        # Should generate variations by removing country and state suffixes
        self.assertIn("South Darfur State, Sudan", variations)  # Original
        self.assertIn("South Darfur", variations)  # Without ", Sudan" and " State"
        self.assertIn("South Darfur State", variations)  # Without ", Sudan"

        # Test with prefix
        variations = self.matcher._generate_name_variations("Fasher")

        # Should add "Al " prefix since it exists in database
        self.assertIn("Fasher", variations)  # Original
        self.assertIn("Al Fasher", variations)  # With prefix

    def test_enhanced_matching_with_country_suffix(self):
        """Test that locations with country suffixes are successfully matched."""
        # This should now match South Darfur
        result = self.matcher.match_location("South Darfur State, Sudan")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "South Darfur")
        self.assertEqual(result.geo_id, "SDN_SD")

    def test_enhanced_matching_with_admin_suffix(self):
        """Test that locations with administrative suffixes are successfully matched."""
        # This should match Khartoum
        result = self.matcher.match_location("Khartoum State")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Khartoum")
        self.assertEqual(result.geo_id, "SDN_KH")

    def test_enhanced_matching_with_geographic_suffix(self):
        """Test that locations with geographic suffixes are successfully matched."""
        # This should match Al Fasher
        result = self.matcher.match_location("Al Fasher City")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Al Fasher")
        self.assertEqual(result.geo_id, "SDN_ND_AF")

    def test_complex_name_matching(self):
        """Test matching complex names with multiple suffixes."""
        # Complex case: "Al Fasher, North Darfur State, Sudan"
        result = self.matcher.match_location("Al Fasher, North Darfur State, Sudan")

        # Should match Al Fasher after removing suffixes
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Al Fasher")

    def test_cache_rebuilding_logic(self):
        """Test that cache rebuilding works correctly based on data changes."""
        # First load - should build cache
        self.matcher._load_suffix_cache()
        initial_timestamp = self.matcher._cache_timestamp

        # Should not rebuild immediately
        self.assertFalse(self.matcher._should_rebuild_cache())

        # Mock old timestamp to test time-based rebuilding
        old_timestamp = timezone.now() - timedelta(hours=2)
        self.matcher._cache_timestamp = old_timestamp

        # Should rebuild due to age
        self.assertTrue(self.matcher._should_rebuild_cache())

    def test_cache_performance_with_repeated_calls(self):
        """Test that caching improves performance for repeated calls."""
        # First call builds cache
        result1 = self.matcher.match_location("South Darfur State, Sudan")

        # Second call should use cache
        result2 = self.matcher.match_location("South Darfur State, Sudan")

        # Results should be identical
        self.assertEqual(result1, result2)
        self.assertIsNotNone(result1)
        self.assertEqual(result1.name, "South Darfur")

    def test_bulk_matching_with_enhanced_variations(self):
        """Test that bulk matching works with enhanced name variations."""
        location_names = ["South Darfur State, Sudan", "North Darfur State, Sudan", "Khartoum State, Sudan", "Al Fasher City"]

        results = self.matcher.bulk_match_locations(location_names)

        # All should be matched
        self.assertEqual(len(results), 4)

        # Check specific matches
        self.assertIsNotNone(results["South Darfur State, Sudan"])
        self.assertEqual(results["South Darfur State, Sudan"].name, "South Darfur")

        self.assertIsNotNone(results["North Darfur State, Sudan"])
        self.assertEqual(results["North Darfur State, Sudan"].name, "North Darfur")

        self.assertIsNotNone(results["Khartoum State, Sudan"])
        self.assertEqual(results["Khartoum State, Sudan"].name, "Khartoum")

        self.assertIsNotNone(results["Al Fasher City"])
        self.assertEqual(results["Al Fasher City"].name, "Al Fasher")

    def test_empty_and_invalid_inputs(self):
        """Test handling of empty and invalid inputs."""
        # Empty string
        result = self.matcher.match_location("")
        self.assertIsNone(result)

        # None input
        result = self.matcher.match_location(None)
        self.assertIsNone(result)

        # Whitespace only
        result = self.matcher.match_location("   ")
        self.assertIsNone(result)

        # Unmatched location (completely fictional)
        result = self.matcher.match_location("Completely Fictional Place")
        self.assertIsNone(result)

    def test_gazetteer_matching_with_variations(self):
        """Test that gazetteer entries are matched with enhanced variations."""
        # Should match via gazetteer entry "Khartoum State"
        result = self.matcher.match_location("Khartoum State, Sudan", source="IDMC")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Khartoum")

    def test_hierarchical_matching_with_parent_context(self):
        """Test matching with parent location context using enhanced variations."""
        # Should match Al Fasher within North Darfur context
        result = self.matcher.match_location("Al Fasher City", parent_location=self.north_darfur)

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Al Fasher")
        self.assertEqual(result.parent, self.north_darfur)

    def test_admin_level_filtering_with_variations(self):
        """Test admin level filtering works with name variations."""
        # Should match state-level location
        result = self.matcher.match_location("South Darfur State, Sudan", admin_level=1)

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "South Darfur")
        self.assertEqual(result.admin_level.code, "1")

        # Should not match locality when looking for state
        result = self.matcher.match_location("Al Fasher City", admin_level=1)

        self.assertIsNone(result)

    @patch("location.utils.logger")
    def test_error_handling_in_cache_loading(self, mock_logger):
        """Test that errors during cache loading are handled gracefully."""
        # Clear existing cache
        self.matcher.clear_cache()

        # Mock database error
        with patch("location.utils.Location.objects.values_list", side_effect=Exception("Database error")):
            # Should not raise exception
            self.matcher._load_suffix_cache()

            # Should log warning
            mock_logger.warning.assert_called()

            # Cache should be in valid state (empty but not None)
            self.assertIsInstance(self.matcher._suffix_cache, dict)

    def test_cache_clear_functionality(self):
        """Test that cache clearing works correctly."""
        # Load cache
        self.matcher._load_suffix_cache()

        # Verify cache is populated
        self.assertIsNotNone(self.matcher._cache_timestamp)
        self.assertTrue(len(self.matcher._suffix_cache) > 0)

        # Clear cache
        self.matcher.clear_cache()

        # Verify cache is cleared
        self.assertIsNone(self.matcher._cache_timestamp)
        self.assertEqual(len(self.matcher._suffix_cache), 0)
        self.assertEqual(len(self.matcher._prefix_cache), 0)

    def test_case_insensitive_matching(self):
        """Test that enhanced matching is case insensitive."""
        # Test various cases
        test_cases = [
            "south darfur state, sudan",
            "SOUTH DARFUR STATE, SUDAN",
            "South Darfur State, Sudan",
            "South DARFUR state, SUDAN",
        ]

        for test_case in test_cases:
            result = self.matcher.match_location(test_case)
            self.assertIsNotNone(result, f"Failed to match: {test_case}")
            self.assertEqual(result.name, "South Darfur")

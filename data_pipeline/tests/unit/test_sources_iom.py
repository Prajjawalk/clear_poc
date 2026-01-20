"""
Unit tests for IOM DTM data source.

Tests focus on key helper methods:
- Location caching and lookup functionality  
- Data validation and processing logic
"""

from unittest.mock import Mock, patch

from django.test import TestCase

from data_pipeline.models import Source, Variable
from data_pipeline.sources.iom import IOM
from location.models import AdmLevel, Location, Gazetteer


class IOMSourceTest(TestCase):
    """Test IOM source implementation."""

    def setUp(self):
        """Create test source and variables."""
        self.source = Source.objects.create(
            name="IOM - International Organization for Migration",
            class_name="IOM",
            base_url="https://dtmapi.iom.int/v3/displacement/admin2",
            is_active=True,
        )

        self.displacement_var = Variable.objects.create(
            source=self.source,
            code="iom_dtm_displacement",
            name="IOM DTM - Displacement Data",
            period="day",
            adm_level=2,
            type="mixed",
        )

        self.iom_source = IOM(self.source)

        # Create test admin level
        self.adm2_level = AdmLevel.objects.create(
            code="2",
            name="Admin Level 2"
        )

        # Create test locations
        self.location1 = Location.objects.create(
            name="Test Location 1",
            admin_level=self.adm2_level,
            geo_id="SD_001_001"
        )

        self.location2 = Location.objects.create(
            name="Test Location 2", 
            admin_level=self.adm2_level,
            geo_id="SD_001_002"
        )

    def test_initialization(self):
        """Test IOM source initialization."""
        self.assertEqual(self.iom_source.source_model, self.source)
        self.assertIsNone(self.iom_source._location_cache)
        self.assertIsNone(self.iom_source._adm2_level)

    def test_location_cache_building_with_gazetteer(self):
        """Test that location cache is built correctly from gazetteer entries."""
        # Create test gazetteer entries
        Gazetteer.objects.create(
            source="IOM_DTM",
            name="Khartoum",
            code="SDN001",
            location=self.location1
        )

        Gazetteer.objects.create(
            source="IOM_DTM", 
            name="Kassala",
            code="SDN002",
            location=self.location2
        )

        # Build cache
        self.iom_source._build_location_cache()

        # Verify cache contains expected entries
        self.assertIsNotNone(self.iom_source._location_cache)
        
        # Check pcode lookups
        self.assertEqual(self.iom_source._location_cache["SDN001"], self.location1)
        self.assertEqual(self.iom_source._location_cache["SDN002"], self.location2)
        
        # Check name lookups (lowercase)
        self.assertEqual(self.iom_source._location_cache["khartoum"], self.location1)
        self.assertEqual(self.iom_source._location_cache["kassala"], self.location2)

    def test_location_cache_building_with_locations(self):
        """Test that location cache includes direct location lookups by geo_id."""
        # Build cache (should include locations by geo_id)
        self.iom_source._build_location_cache()

        # Verify cache contains geo_id entries
        self.assertIsNotNone(self.iom_source._location_cache)
        self.assertEqual(self.iom_source._location_cache["geo_SD_001_001"], self.location1)
        self.assertEqual(self.iom_source._location_cache["geo_SD_001_002"], self.location2)

    def test_location_cache_only_built_once(self):
        """Test that location cache is only built once for performance."""
        # First call should build cache
        self.iom_source._build_location_cache()
        self.assertIsNotNone(self.iom_source._location_cache)
        
        # Store reference to cache
        first_cache = self.iom_source._location_cache
        
        # Second call should not rebuild cache
        self.iom_source._build_location_cache()
        self.assertIs(self.iom_source._location_cache, first_cache)

    def test_location_lookup_direct_pcode(self):
        """Test location lookup by direct pcode."""
        # Setup cache with test data
        Gazetteer.objects.create(
            source="IOM_DTM",
            name="Test City",
            code="TEST001", 
            location=self.location1
        )

        # Test direct pcode lookup
        result = self.iom_source._lookup_location("TEST001")
        self.assertEqual(result, self.location1)

    def test_location_lookup_geo_id(self):
        """Test location lookup by geo_id."""
        # Test geo_id lookup (should work after cache is built)
        result = self.iom_source._lookup_location("SD_001_001")
        self.assertEqual(result, self.location1)

    def test_location_lookup_name_case_insensitive(self):
        """Test location lookup by name (case insensitive)."""
        # Setup cache with test data
        Gazetteer.objects.create(
            source="IOM_DTM",
            name="Test City",
            code="TEST001", 
            location=self.location1
        )

        # Test case insensitive name lookup
        result = self.iom_source._lookup_location("test city")
        self.assertEqual(result, self.location1)

        result = self.iom_source._lookup_location("TEST CITY")
        self.assertEqual(result, self.location1)

    def test_location_lookup_no_match(self):
        """Test location lookup with no matching entry."""
        result = self.iom_source._lookup_location("NONEXISTENT")
        self.assertIsNone(result)

    def test_location_lookup_auto_builds_cache(self):
        """Test that location lookup automatically builds cache if needed."""
        # Cache should be None initially
        self.assertIsNone(self.iom_source._location_cache)
        
        # Lookup should trigger cache building
        self.iom_source._lookup_location("TEST001")
        
        # Cache should now be built
        self.assertIsNotNone(self.iom_source._location_cache)

    def test_location_lookup_multiple_strategies(self):
        """Test that location lookup tries multiple strategies in order."""
        # Setup gazetteer entry
        Gazetteer.objects.create(
            source="IOM_DTM",
            name="Multi Test",
            code="MULTI001", 
            location=self.location1
        )

        # Test that direct pcode lookup works
        result = self.iom_source._lookup_location("MULTI001")
        self.assertEqual(result, self.location1)

        # Test that if we look up by geo_id, it still finds the location
        result = self.iom_source._lookup_location("SD_001_001")
        self.assertEqual(result, self.location1)

        # Test that name lookup also works
        result = self.iom_source._lookup_location("multi test")
        self.assertEqual(result, self.location1)

    def test_location_lookup_with_empty_cache(self):
        """Test location lookup behavior when cache is empty."""
        # Force build cache to ensure it's empty but initialized
        self.iom_source._build_location_cache()
        
        # Should return None for non-existent lookup
        result = self.iom_source._lookup_location("DOESNOTEXIST")
        self.assertIsNone(result)
"""Location matching utilities for geographic data processing."""

import logging
from difflib import SequenceMatcher

from django.db.models import Q
from django.utils import timezone

from .models import Gazetteer, Location

logger = logging.getLogger(__name__)


def _calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity between two strings using SequenceMatcher.
    
    Args:
        str1: First string to compare
        str2: Second string to compare
        
    Returns:
        Float between 0 and 1 representing similarity (1 = identical)
    """
    if not str1 or not str2:
        return 0.0

    # Normalize strings for comparison
    s1 = str1.lower().strip()
    s2 = str2.lower().strip()

    if s1 == s2:
        return 1.0

    return SequenceMatcher(None, s1, s2).ratio()


class LocationMatcher:
    """Utility class for matching location names to database locations."""

    def __init__(self):
        """Initialize location matcher with caching."""
        self._location_cache: dict[str, Location] = {}
        self._gazetteer_cache: dict[str, dict[str, list[Gazetteer]]] = {}
        self._suffix_cache: dict[str, set[str]] = {}
        self._prefix_cache: set[str] = set()
        self._cache_timestamp = None

    def match_location(
        self,
        location_name: str,
        source: str = None,
        admin_level: int = None,
        parent_location: Location = None,
        context_data: dict = None,
    ) -> Location | None:
        """Match location name to Location instance using hierarchical matching strategy.

        Implements three-tier matching approach:
        1. Current source gazetteer (with admin level prioritization)
        2. Direct Location model queries
        3. Other source gazetteers as fallback

        Args:
            location_name: Name to match
            source: Data source name for gazetteer lookup
            admin_level: Expected administrative level
            parent_location: Parent location for hierarchical matching
            context_data: Additional context for improved matching

        Returns:
            Location instance if match found, None otherwise
        """
        if not location_name or not location_name.strip():
            return None

        location_name = location_name.strip()
        cache_key = f"{location_name}:{source}:{admin_level}:{parent_location.id if parent_location else None}"

        # Check cache first
        if cache_key in self._location_cache:
            return self._location_cache[cache_key]

        context_data = context_data or {}
        expected_admin_level = context_data.get("expected_admin_level") or admin_level

        location = self._hierarchical_location_match(
            location_name, source, expected_admin_level, parent_location, context_data
        )

        # Cache result
        self._location_cache[cache_key] = location

        if location:
            logger.debug(f"Matched '{location_name}' to {location.geo_id}")
        else:
            logger.warning(f"No match found for location '{location_name}'")

        return location

    def _hierarchical_location_match(
        self,
        location_name: str,
        source: str = None,
        admin_level: int = None,
        parent_location: Location = None,
        context_data: dict = None,
    ) -> Location | None:
        """Implement hierarchical location matching strategy.
        
        Three-tier approach:
        1. Current source gazetteer (prioritizing same admin level)
        2. Direct Location model queries
        3. Other source gazetteers as fallback
        """
        location = None
        
        # STEP 1: Try matching from gazetteer filtered on current source
        if source:
            location = self._match_from_current_source_gazetteer(
                location_name, source, admin_level, parent_location
            )
        
        # STEP 2: Try direct Location model match if no gazetteer match
        if not location:
            location = self._match_from_location_model(
                location_name, admin_level, parent_location
            )
        
        # STEP 3: Try gazetteer from other sources as last resort
        if not location:
            location = self._match_from_other_source_gazetteers(
                location_name, source, admin_level, parent_location
            )
        
        return location

    def _match_from_current_source_gazetteer(
        self,
        location_name: str,
        source: str,
        admin_level: int = None,
        parent_location: Location = None,
    ) -> Location | None:
        """Match from gazetteer filtered on current source with admin level priority."""
        
        # 1a. Exact match by name (prioritizing same admin level)
        location = self._exact_gazetteer_match(location_name, source, admin_level, parent_location)
        if location:
            return location
        
        # 1b. Exact match by code/alternative identifier
        try:
            query = Q(code__iexact=location_name, source=source)
            if admin_level is not None:
                query &= Q(location__admin_level__code=str(admin_level))
            if parent_location:
                query &= Q(location__parent=parent_location)
            
            gazetteer_entry = Gazetteer.objects.select_related("location").get(query)
            return gazetteer_entry.location
        except (Gazetteer.DoesNotExist, Gazetteer.MultipleObjectsReturned):
            pass
        
        # 1c. Fuzzy match by name within the same source
        try:
            query = Q(source=source)
            if admin_level is not None:
                query &= Q(location__admin_level__code=str(admin_level))
            if parent_location:
                query &= Q(location__parent=parent_location)
            
            candidates = Gazetteer.objects.select_related("location").filter(query)
            
            best_match = None
            best_similarity = 0.0
            min_similarity = 0.8  # High threshold for fuzzy matching
            
            for candidate in candidates:
                similarity = _calculate_similarity(location_name, candidate.name)
                if similarity > best_similarity and similarity >= min_similarity:
                    best_similarity = similarity
                    best_match = candidate.location
            
            if best_match:
                return best_match
        except Exception:
            pass
        
        return None

    def _match_from_location_model(
        self,
        location_name: str,
        admin_level: int = None,
        parent_location: Location = None,
    ) -> Location | None:
        """Match directly from Location model."""
        
        # 2a. Exact match by name
        location = self._exact_location_match(location_name, admin_level, parent_location)
        if location:
            return location
        
        # 2b. Exact match by geo_id (Location primary identifier)
        try:
            query = Q(geo_id__iexact=location_name)
            
            if admin_level is not None:
                query &= Q(admin_level__code=str(admin_level))
            if parent_location:
                query &= Q(parent=parent_location)
            
            return Location.objects.get(query)
        except (Location.DoesNotExist, Location.MultipleObjectsReturned):
            pass
        
        # 2c. Try name variations (with/without common prefixes/suffixes)
        variations = self._generate_name_variations(location_name)
        all_matches = []
        for variation in variations:
            location = self._exact_location_match(variation, admin_level, parent_location)
            if location:
                all_matches.append((location, variation))
        
        # If we have matches, prefer more specific locations (higher admin level codes)
        if all_matches:
            return self._select_best_match(all_matches, location_name)
        
        return None
    
    def _select_best_match(self, matches: list[tuple], original_name: str) -> Location:
        """Select the best match from multiple candidates."""
        # Sort by admin level code (higher codes are more specific) and name similarity
        def match_score(match_tuple):
            location, variation = match_tuple
            admin_code = int(location.admin_level.code) if location.admin_level.code.isdigit() else 0
            
            # Calculate similarity to original name
            from difflib import SequenceMatcher
            name_similarity = SequenceMatcher(None, original_name.lower(), location.name.lower()).ratio()
            
            # Prefer higher admin levels (more specific) and better name similarity
            return (admin_code, name_similarity)
        
        # Sort by score and return the best match
        best_match = max(matches, key=match_score)
        return best_match[0]

    def _match_from_other_source_gazetteers(
        self,
        location_name: str,
        current_source: str,
        admin_level: int = None,
        parent_location: Location = None,
    ) -> Location | None:
        """Match from gazetteers of other sources as last resort."""
        
        # 3a. Exact match by name from other sources
        try:
            query = Q(name__iexact=location_name)
            if current_source:
                query &= ~Q(source=current_source)  # Exclude current source
            if admin_level is not None:
                query &= Q(location__admin_level__code=str(admin_level))
            if parent_location:
                query &= Q(location__parent=parent_location)
            
            gazetteer_entry = Gazetteer.objects.select_related("location").get(query)
            return gazetteer_entry.location
        except (Gazetteer.DoesNotExist, Gazetteer.MultipleObjectsReturned):
            pass
        
        # 3b. Fuzzy match with variations from other sources
        variations = self._generate_name_variations(location_name)
        for variation in variations:
            try:
                query = Q(name__icontains=variation)
                if current_source:
                    query &= ~Q(source=current_source)
                if admin_level is not None:
                    query &= Q(location__admin_level__code=str(admin_level))
                if parent_location:
                    query &= Q(location__parent=parent_location)
                
                candidates = Gazetteer.objects.select_related("location").filter(query)
                
                best_match = None
                best_similarity = 0.0
                min_similarity = 0.75  # Lower threshold for other sources
                
                for candidate in candidates:
                    similarity = _calculate_similarity(location_name, candidate.name)
                    if similarity > best_similarity and similarity >= min_similarity:
                        best_similarity = similarity
                        best_match = candidate.location
                
                if best_match:
                    return best_match
            except Exception:
                continue
        
        return None

    def _generate_name_variations(self, location_name: str) -> list[str]:
        """Generate variations using database-derived suffixes and prefixes."""
        self._load_suffix_cache()  # Lazy load
        
        variations = [location_name]
        
        # Generate variations by removing suffixes (including chained removal)
        self._add_suffix_variations(location_name, variations)
        
        # Add prefix variations
        self._add_prefix_variations(location_name, variations)
        
        return list(set(variations))  # Remove duplicates
        
    def _add_suffix_variations(self, location_name: str, variations: list[str]):
        """Add variations by removing suffixes, including chained removal."""
        all_suffixes = self._suffix_cache.get('all', set())
        
        # Use a queue to handle chained suffix removal
        to_process = [location_name]
        processed = set()
        
        while to_process:
            current_name = to_process.pop(0)
            
            if current_name in processed:
                continue
            processed.add(current_name)
            
            current_lower = current_name.lower()
            
            # Try removing each suffix
            for suffix in all_suffixes:
                if current_lower.endswith(suffix.lower()):
                    clean_name = current_name[:-len(suffix)].strip()
                    if clean_name and clean_name not in processed:
                        variations.append(clean_name)
                        to_process.append(clean_name)  # Process this for further suffix removal
        
        # Additional fallback: try comma-separated parsing for complex location names
        self._add_comma_variations(location_name, variations)
    
    def _add_comma_variations(self, location_name: str, variations: list[str]):
        """Add variations by parsing comma-separated location names."""
        if ',' in location_name:
            parts = [part.strip() for part in location_name.split(',')]
            
            # Add individual parts (except very short ones that are likely articles)
            for part in parts:
                if len(part) > 2 and part not in variations:
                    variations.append(part)
            
            # Add combinations of adjacent parts
            for i in range(len(parts) - 1):
                combined = ', '.join(parts[i:i+2])
                if combined not in variations:
                    variations.append(combined)
                    
                # Also add without comma
                combined_no_comma = ' '.join(parts[i:i+2])
                if combined_no_comma not in variations:
                    variations.append(combined_no_comma)

    def bulk_match_locations(
        self,
        location_names: list[str],
        source: str = None,
        admin_level: int = None,
        parent_location: Location = None,
    ) -> dict[str, Location | None]:
        """Match multiple location names efficiently using exact matching only.

        Args:
            location_names: List of names to match
            source: Data source name
            admin_level: Expected administrative level
            parent_location: Parent location for hierarchical matching

        Returns:
            Dictionary mapping location names to Location instances
        """
        results = {}

        # Pre-load gazetteer data for this source if specified
        if source and source not in self._gazetteer_cache:
            self._load_gazetteer_cache(source)

        for name in location_names:
            results[name] = self.match_location(name, source, admin_level, parent_location)

        return results

    def _exact_gazetteer_match(
        self,
        location_name: str,
        source: str,
        admin_level: int = None,
        parent_location: Location = None,
    ) -> Location | None:
        """Try exact match in gazetteer (both English and Arabic names)."""
        try:
            query = Q(name__iexact=location_name, source=source)

            if admin_level is not None:
                query &= Q(location__admin_level__code=str(admin_level))

            if parent_location:
                query &= Q(location__parent=parent_location)

            gazetteer_entry = Gazetteer.objects.select_related("location").get(query)
            return gazetteer_entry.location

        except Gazetteer.DoesNotExist:
            return None
        except Gazetteer.MultipleObjectsReturned:
            # Multiple matches - try to be more specific
            entries = Gazetteer.objects.select_related("location").filter(query)
            if parent_location:
                # Prefer matches within the specified parent
                parent_matches = entries.filter(location__parent=parent_location)
                if parent_matches.exists():
                    return parent_matches.first().location
            return entries.first().location

    def _exact_location_match(
        self,
        location_name: str,
        admin_level: int = None,
        parent_location: Location = None,
    ) -> Location | None:
        """Try exact match in location names (both English and Arabic)."""
        try:
            # Try English name first
            query = Q(name__iexact=location_name)

            if admin_level is not None:
                query &= Q(admin_level__code=str(admin_level))

            if parent_location:
                query &= Q(parent=parent_location)

            return Location.objects.get(query)

        except Location.DoesNotExist:
            # Try Arabic name if English didn't match
            try:
                query = Q(name_ar__iexact=location_name)

                if admin_level is not None:
                    query &= Q(admin_level__code=str(admin_level))

                if parent_location:
                    query &= Q(parent=parent_location)

                return Location.objects.get(query)

            except Location.DoesNotExist:
                return None
            except Location.MultipleObjectsReturned:
                locations = Location.objects.filter(query)
                if parent_location:
                    parent_matches = locations.filter(parent=parent_location)
                    if parent_matches.exists():
                        return parent_matches.first()
                return locations.first()

        except Location.MultipleObjectsReturned:
            locations = Location.objects.filter(query)
            if parent_location:
                parent_matches = locations.filter(parent=parent_location)
                if parent_matches.exists():
                    return parent_matches.first()
            return locations.first()

    def _load_gazetteer_cache(self, source: str):
        """Load gazetteer data for a source into cache."""
        self._gazetteer_cache[source] = {}

        entries = Gazetteer.objects.select_related("location", "location__admin_level").filter(source=source)

        for entry in entries:
            admin_code = entry.location.admin_level.code
            if admin_code not in self._gazetteer_cache[source]:
                self._gazetteer_cache[source][admin_code] = []
            self._gazetteer_cache[source][admin_code].append(entry)

    def get_locations_at_level(self, admin_level: int, parent: Location = None) -> list[Location]:
        """Get all locations at a specific administrative level."""
        query = Q(admin_level__code=str(admin_level))

        if parent:
            query &= Q(parent=parent)

        return list(Location.objects.filter(query).order_by("geo_id"))

    def get_location_hierarchy(self, location: Location) -> list[Location]:
        """Get full hierarchical path for a location."""
        return location.get_full_hierarchy()

    def get_all_locations_for_manual_review(self, admin_level: int = None, limit: int = 100) -> list[Location]:
        """Get locations for manual gazetteer entry review.

        Args:
            admin_level: Filter by administrative level
            limit: Maximum number of locations to return

        Returns:
            List of Location objects
        """
        locations_query = Location.objects.all().order_by("name")

        if admin_level is not None:
            locations_query = locations_query.filter(admin_level__code=str(admin_level))

        return list(locations_query[:limit])

    def _should_rebuild_cache(self) -> bool:
        """Check if suffix cache needs rebuilding based on data changes."""
        if not self._cache_timestamp:
            return True
            
        # Check if new locations/gazetteer entries added since last cache
        cache_age = timezone.now() - self._cache_timestamp
        
        # Rebuild cache if it's older than 1 hour and there's new data
        if cache_age.total_seconds() > 3600:
            recent_locations = Location.objects.filter(
                created_at__gt=self._cache_timestamp
            ).exists()
            
            # Check if UnmatchedLocation model exists (might not in all deployments)
            try:
                from .models import UnmatchedLocation
                recent_unmatched = UnmatchedLocation.objects.filter(
                    first_seen__gt=self._cache_timestamp
                ).exists()
            except ImportError:
                recent_unmatched = False
            
            return recent_locations or recent_unmatched
        
        return False

    def _pluralize(self, word: str) -> str:
        """Apply English pluralization rules."""
        word = word.lower()
        
        # Handle common irregular plurals
        irregular_plurals = {
            'child': 'children',
            'person': 'people',
            'man': 'men',
            'woman': 'women',
            'foot': 'feet',
            'tooth': 'teeth',
        }
        
        if word in irregular_plurals:
            return irregular_plurals[word]
        
        # Standard pluralization rules
        if word.endswith('s') or word.endswith('ss') or word.endswith('sh') or \
           word.endswith('ch') or word.endswith('x') or word.endswith('z'):
            return word + 'es'
        elif word.endswith('y') and len(word) > 1 and word[-2] not in 'aeiou':
            return word[:-1] + 'ies'
        elif word.endswith('f'):
            return word[:-1] + 'ves'
        elif word.endswith('fe'):
            return word[:-2] + 'ves'
        elif word.endswith('o') and len(word) > 1 and word[-2] not in 'aeiou':
            return word + 'es'
        else:
            return word + 's'

    def _load_suffix_cache(self):
        """Extract common suffixes from existing location and gazetteer data."""
        if self._suffix_cache and not self._should_rebuild_cache():
            return  # Use existing cache
            
        logger.debug("Loading suffix cache from database")
        
        # Clear existing cache
        self._suffix_cache.clear()
        
        # 1. Extract admin level suffixes from AdmLevel names
        admin_suffixes = set()
        try:
            from .models import AdmLevel
            for level in AdmLevel.objects.all():
                level_name = level.name.lower()
                admin_suffixes.add(f" {level_name}")
                # Add plural forms with proper English pluralization
                if not level_name.endswith('s'):
                    plural = self._pluralize(level_name)
                    admin_suffixes.add(f" {plural}")
        except Exception as e:
            logger.warning(f"Could not load admin level suffixes: {e}")
        
        # 2. Extract country suffixes by analyzing existing data patterns
        country_suffixes = set()
        try:
            # Look for patterns in unmatched locations
            from .models import UnmatchedLocation
            unmatched_names = UnmatchedLocation.objects.values_list('name', flat=True)
            
            for name in unmatched_names:
                name_lower = name.lower()
                # Look for ", countryname" patterns
                if ', ' in name_lower:
                    potential_country = name_lower.split(', ')[-1].strip()
                    # Countries are usually 1-2 words
                    if len(potential_country.split()) <= 2:
                        country_suffixes.add(f", {potential_country}")
        except ImportError:
            # UnmatchedLocation model might not exist in all deployments
            logger.debug("UnmatchedLocation model not available, skipping country suffix detection")
        except Exception as e:
            logger.warning(f"Could not analyze unmatched locations: {e}")
        
        # 3. Extract geographic suffixes from location names
        geographic_suffixes = set()
        try:
            all_names = list(Location.objects.values_list('name', flat=True))
            all_names.extend(Gazetteer.objects.values_list('name', flat=True))
            
            # Common geographic terms that might be suffixes
            common_geo_terms = {
                'city', 'town', 'village', 'district', 'area', 'zone',
                'province', 'region', 'territory', 'division', 'department'
            }
            
            for name in all_names:
                words = name.lower().split()
                if len(words) > 1 and words[-1] in common_geo_terms:
                    geographic_suffixes.add(f" {words[-1]}")
        except Exception as e:
            logger.warning(f"Could not extract geographic suffixes: {e}")
        
        # Store in cache by category
        self._suffix_cache['admin'] = admin_suffixes
        self._suffix_cache['country'] = country_suffixes  
        self._suffix_cache['geographic'] = geographic_suffixes
        
        # Create combined list for quick access
        self._suffix_cache['all'] = admin_suffixes | country_suffixes | geographic_suffixes
        
        # Load prefix cache as well
        self._load_prefix_cache()
        
        # Update timestamp
        self._cache_timestamp = timezone.now()
        
        logger.debug(f"Loaded {len(self._suffix_cache['all'])} suffixes: admin={len(admin_suffixes)}, country={len(country_suffixes)}, geographic={len(geographic_suffixes)}")

    def _load_prefix_cache(self):
        """Extract common prefixes from existing location data."""
        try:
            # Get all location names
            all_names = list(Location.objects.values_list('name', flat=True))
            all_names.extend(Gazetteer.objects.values_list('name', flat=True))
            
            # Look for common directional and article prefixes
            potential_prefixes = {'al ', 'el ', 'the ', 'north ', 'south ', 'east ', 'west ', 'central ', 'upper ', 'lower '}
            
            self._prefix_cache.clear()
            for name in all_names:
                name_lower = name.lower()
                for prefix in potential_prefixes:
                    if name_lower.startswith(prefix):
                        self._prefix_cache.add(prefix)
            
            logger.debug(f"Loaded {len(self._prefix_cache)} prefixes from database")
        except Exception as e:
            logger.warning(f"Could not load prefix cache: {e}")

    def _add_prefix_variations(self, location_name: str, variations: list[str]):
        """Add prefix variations based on existing location patterns."""
        base_name = location_name.lower()
        
        # If no prefix exists, try adding common ones found in database
        has_prefix = any(base_name.startswith(prefix) for prefix in self._prefix_cache)
        if not has_prefix:
            for prefix in self._prefix_cache:
                prefixed_name = f"{prefix.title()}{location_name}"
                variations.append(prefixed_name)
        
        # If prefix exists, try removing it
        for prefix in self._prefix_cache:
            if base_name.startswith(prefix):
                clean_name = location_name[len(prefix):].strip()
                if clean_name:
                    variations.append(clean_name)

    def clear_cache(self):
        """Clear internal caches."""
        self._location_cache.clear()
        self._gazetteer_cache.clear()
        self._suffix_cache.clear()
        self._prefix_cache.clear()
        self._cache_timestamp = None


# Global instance for easy access
location_matcher = LocationMatcher()

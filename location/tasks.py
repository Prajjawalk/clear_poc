"""Celery tasks for location processing."""

import logging
from datetime import UTC, datetime

from celery import shared_task
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def compute_potential_matches(self, unmatched_location_id: int):
    """Precompute potential location matches for an unmatched location.

    This task runs in the background to avoid blocking the main data processing
    pipeline while still providing helpful matching suggestions.

    Args:
        unmatched_location_id: ID of the UnmatchedLocation to process

    Returns:
        dict: Results summary including number of matches found
    """
    try:
        from location.models import Gazetteer, Location, UnmatchedLocation
        from location.utils import _calculate_similarity

        # Get the unmatched location
        try:
            unmatched = UnmatchedLocation.objects.get(id=unmatched_location_id)
        except UnmatchedLocation.DoesNotExist:
            logger.error(f"UnmatchedLocation {unmatched_location_id} not found")
            return {"error": "UnmatchedLocation not found"}

        logger.info(f"Computing potential matches for: {unmatched.name}")

        # Check if matches have already been computed recently
        if unmatched.potential_matches_computed_at:
            logger.info(f"Potential matches already computed for '{unmatched.name}' at {unmatched.potential_matches_computed_at}")
            return {
                "unmatched_location_id": unmatched_location_id,
                "location_name": unmatched.name,
                "matches_found": len(unmatched.potential_matches or []),
                "top_similarity": unmatched.potential_matches[0]["similarity_score"] if unmatched.potential_matches else 0,
                "computed_at": unmatched.potential_matches_computed_at.isoformat(),
                "skipped": True,
            }

        potential_matches = []
        query_name = unmatched.name.lower().strip()

        # Search through locations with database-level filtering
        # PERFORMANCE: Use database queries to filter candidates before similarity calculation

        if not query_name or len(query_name) < 2:
            logger.warning(f"Query name too short: '{query_name}'")
            return {"matches_found": 0}

        # Step 1: Get exact matches first (fastest)
        exact_matches = Location.objects.select_related("admin_level").filter(Q(name__iexact=unmatched.name) | Q(name_ar__iexact=unmatched.name))[:10]

        for location in exact_matches:
            potential_matches.append(
                {
                    "location_id": location.id,
                    "location_name": location.name,
                    "location_name_ar": getattr(location, "name_ar", ""),
                    "admin_level": location.admin_level.name,
                    "admin_level_code": location.admin_level.code,
                    "geo_id": location.geo_id,
                    "matched_name": location.name,
                    "similarity_score": 1.0,
                    "match_source": "exact",
                }
            )

        # Step 2: Get partial matches if we need more results
        if len(potential_matches) < 10:
            # Use database filtering to get candidates
            query_prefix = query_name[:3] if len(query_name) > 3 else query_name
            query_suffix = query_name[-3:] if len(query_name) > 3 else query_name

            # Get location candidates with database-level filtering
            location_candidates = (
                Location.objects.select_related("admin_level")
                .filter(Q(name__icontains=query_prefix) | Q(name__icontains=query_suffix) | Q(name__istartswith=query_prefix))
                .exclude(id__in=[m["location_id"] for m in potential_matches])[:100]
            )  # Limit candidates

            # Calculate similarities only for these pre-filtered candidates
            for location in location_candidates:
                name = location.name.lower().strip()
                if not name:
                    continue

                # Calculate similarity with primary name
                similarity = _calculate_similarity(query_name, name)

                # Also check Arabic name if available
                similarity_ar = 0
                name_ar = getattr(location, "name_ar", "")
                if name_ar and query_name:
                    name_ar_lower = name_ar.lower().strip()
                    similarity_ar = _calculate_similarity(query_name, name_ar_lower)

                # Use the higher similarity score
                final_similarity = max(similarity, similarity_ar)

                # Higher threshold to reduce low-quality matches
                if final_similarity >= 0.4:
                    potential_matches.append(
                        {
                            "location_id": location.id,
                            "location_name": location.name,
                            "location_name_ar": getattr(location, "name_ar", ""),
                            "admin_level": location.admin_level.name,
                            "admin_level_code": location.admin_level.code,
                            "geo_id": location.geo_id,
                            "matched_name": location.name,
                            "similarity_score": round(final_similarity, 3),
                            "match_source": "primary",
                        }
                    )

        # Step 3: Check gazetteer only if we still need more matches
        if len(potential_matches) < 10:
            # Limit gazetteer search to main sources and use database filtering
            gazetteer_candidates = Gazetteer.objects.select_related(
                "location", "location__admin_level"
            ).filter(
                Q(name__icontains=query_prefix) | Q(name__icontains=query_suffix) | Q(name__istartswith=query_prefix),
                source__in=["UNOCHA", "OpenStreetMap", "IDMC"],  # Limit to main sources
            )[:50]  # Limit candidates

            for gazetteer in gazetteer_candidates:
                name = gazetteer.name.lower().strip()
                if not name:
                    continue

                similarity = _calculate_similarity(query_name, name)

                if similarity >= 0.4:
                    # Check if we already have this location
                    existing = next((m for m in potential_matches if m["location_id"] == gazetteer.location.id), None)
                    if not existing or similarity > existing["similarity_score"]:
                        if existing:
                            potential_matches.remove(existing)
                        potential_matches.append(
                            {
                                "location_id": gazetteer.location.id,
                                "location_name": gazetteer.location.name,
                                "location_name_ar": getattr(gazetteer.location, "name_ar", ""),
                                "admin_level": gazetteer.location.admin_level.name,
                                "admin_level_code": gazetteer.location.admin_level.code,
                                "geo_id": gazetteer.location.geo_id,
                                "matched_name": gazetteer.name,
                                "similarity_score": round(similarity, 3),
                                "match_source": f"gazetteer_{gazetteer.source}",
                            }
                        )

        # Deduplicate by location_id, keeping the best match for each location
        location_matches = {}
        for match in potential_matches:
            location_id = match["location_id"]
            if location_id not in location_matches or match["similarity_score"] > location_matches[location_id]["similarity_score"]:
                location_matches[location_id] = match

        # Convert back to list and sort by similarity score (highest first), then take top 15
        deduplicated_matches = list(location_matches.values())
        deduplicated_matches.sort(key=lambda x: x["similarity_score"], reverse=True)
        top_matches = deduplicated_matches[:15]

        # Update the unmatched location with computed matches
        with transaction.atomic():
            unmatched.potential_matches = top_matches
            unmatched.potential_matches_computed_at = datetime.now(UTC)
            unmatched.save(update_fields=["potential_matches", "potential_matches_computed_at"])

        result = {
            "unmatched_location_id": unmatched_location_id,
            "location_name": unmatched.name,
            "matches_found": len(top_matches),
            "top_similarity": top_matches[0]["similarity_score"] if top_matches else 0,
            "computed_at": unmatched.potential_matches_computed_at.isoformat(),
        }

        logger.info(f"Found {len(top_matches)} potential matches for '{unmatched.name}' (best: {result['top_similarity']})")

        return result

    except Exception as e:
        logger.error(f"Error computing potential matches for {unmatched_location_id}: {str(e)}")

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 60 * (2**self.request.retries)  # 1min, 2min, 4min
            raise self.retry(countdown=countdown, exc=e)

        # After max retries, return error
        return {"error": str(e), "unmatched_location_id": unmatched_location_id}


@shared_task
def recompute_all_potential_matches():
    """Recompute potential matches for all pending unmatched locations.

    This can be run as a maintenance task to refresh all suggestions.
    """
    from location.models import UnmatchedLocation

    logger.info("Starting batch recomputation of potential matches")

    # Get all unmatched locations that need computation
    unmatched_locations = UnmatchedLocation.objects.filter(status="pending", potential_matches_computed_at__isnull=True)

    total_count = unmatched_locations.count()
    logger.info(f"Found {total_count} unmatched locations to process")

    # Queue individual computation tasks
    task_ids = []
    for unmatched in unmatched_locations:
        task = compute_potential_matches.delay(unmatched.id)
        task_ids.append(task.id)

    logger.info(f"Queued {len(task_ids)} computation tasks")

    return {"total_locations": total_count, "tasks_queued": len(task_ids), "task_ids": task_ids}

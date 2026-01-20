"""API endpoints for data pipeline operations including location updates."""

import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
import json

from .models import VariableData
from location.models import UnmatchedLocation

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def update_locations(request):
    """
    API endpoint to update VariableData records when locations are matched.
    
    Called by the location app when unmatched locations are resolved.
    Updates all VariableData records with matching original_location_text.
    """
    try:
        data = json.loads(request.body)
        unmatched_location_ids = data.get('unmatched_location_ids', [])
        action = data.get('action', '')
        
        if action != 'update_matched_locations':
            return JsonResponse({
                'success': False,
                'error': f'Unknown action: {action}'
            }, status=400)
        
        if not unmatched_location_ids:
            return JsonResponse({
                'success': True,
                'message': 'No locations to update',
                'updated_count': 0
            })
        
        total_updated = 0
        
        # Process each unmatched location
        for unmatched_id in unmatched_location_ids:
            try:
                # Get the unmatched location with its resolved location
                unmatched = UnmatchedLocation.objects.get(
                    id=unmatched_id,
                    is_matched=True
                )
                
                if not unmatched.resolved_location:
                    logger.warning(f"UnmatchedLocation {unmatched_id} marked as matched but has no resolved_location")
                    continue
                
                # Find all VariableData records linked to this unmatched location
                # Use direct foreign key relationship for efficiency
                matching_records = VariableData.objects.filter(
                    unmatched_location_id=unmatched_id
                )
                
                # Update records individually to handle unique constraint conflicts gracefully
                updated = 0
                skipped = 0
                
                for record in matching_records:
                    # Check if updating this record would create a unique constraint violation
                    conflict_exists = VariableData.objects.filter(
                        variable=record.variable,
                        start_date=record.start_date,
                        end_date=record.end_date,
                        gid=unmatched.resolved_location
                    ).exclude(id=record.id).exists()
                    
                    if conflict_exists:
                        # Skip this record to avoid constraint violation
                        logger.warning(f"Skipping update for VariableData {record.id} due to existing record with same variable/date/location")
                        skipped += 1
                        continue
                    
                    # Safe to update this record
                    try:
                        VariableData.objects.filter(id=record.id).update(
                            gid=unmatched.resolved_location,
                            unmatched_location=None
                        )
                        updated += 1
                    except Exception as e:
                        logger.error(f"Failed to update VariableData {record.id}: {str(e)}")
                        skipped += 1
                
                if skipped > 0:
                    logger.info(f"Updated {updated} VariableData records, skipped {skipped} due to conflicts for location '{unmatched.name}' -> '{unmatched.resolved_location.name}'")
                else:
                    logger.info(f"Updated {updated} VariableData records for location '{unmatched.name}' -> '{unmatched.resolved_location.name}'")

                total_updated += updated
                
            except UnmatchedLocation.DoesNotExist:
                logger.warning(f"UnmatchedLocation {unmatched_id} not found or not matched")
                continue
            except Exception as e:
                logger.error(f"Error processing UnmatchedLocation {unmatched_id}: {str(e)}")
                continue
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully updated {total_updated} data records',
            'updated_count': total_updated
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in update_locations: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def health(request):
    """Health check endpoint for the pipeline API."""
    return JsonResponse({
        'status': 'healthy',
        'service': 'data_pipeline_api'
    })
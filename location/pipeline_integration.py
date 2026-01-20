"""Pipeline API integration utilities for triggering location updates."""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class PipelineAPIError(Exception):
    """Custom exception for pipeline API errors."""

    pass


def trigger_location_updates(unmatched_location_ids: list[int]) -> dict:
    """
    Trigger pipeline API to update source data with newly matched locations.

    Args:
        unmatched_location_ids: List of UnmatchedLocation IDs that were just matched

    Returns:
        Dict with API response details

    Raises:
        PipelineAPIError: If API call fails
    """
    if not unmatched_location_ids:
        return {"success": True, "message": "No locations to update", "updated_count": 0}

    base_url = getattr(settings, "PIPELINE_API_BASE_URL", None)
    endpoint = getattr(settings, "PIPELINE_API_UPDATE_ENDPOINT", "update-locations/")
    timeout = getattr(settings, "PIPELINE_API_TIMEOUT", 30)

    if not base_url:
        logger.warning("PIPELINE_API_BASE_URL not configured - skipping API call")
        return {"success": False, "error": "Pipeline API not configured"}

    # Ensure trailing slash for Django APPEND_SLASH compatibility
    api_url = f"{base_url.rstrip('/')}/{endpoint.strip('/')}/"

    payload = {"unmatched_location_ids": unmatched_location_ids, "action": "update_matched_locations"}

    try:
        logger.info(f"Triggering pipeline API update for {len(unmatched_location_ids)} locations")

        response = requests.post(api_url, json=payload, timeout=timeout, headers={"Content-Type": "application/json", "User-Agent": "NRC-EWAS-Location-App/1.0"})

        response.raise_for_status()

        result = response.json()
        logger.info(f"Pipeline API update successful: {result}")

        return {"success": True, "updated_count": result.get("updated_count", 0), "message": result.get("message", "Update triggered successfully"), "details": result}

    except requests.exceptions.Timeout:
        error_msg = f"Pipeline API timeout after {timeout}s"
        logger.error(error_msg)
        raise PipelineAPIError(error_msg)

    except requests.exceptions.ConnectionError as e:
        error_msg = f"Pipeline API connection error: {str(e)}"
        logger.error(error_msg)
        raise PipelineAPIError(error_msg)

    except requests.exceptions.HTTPError as e:
        error_msg = f"Pipeline API HTTP error: {e.response.status_code} - {e.response.text}"
        logger.error(error_msg)
        raise PipelineAPIError(error_msg)

    except (ValueError, KeyError) as e:
        error_msg = f"Invalid API response: {str(e)}"
        logger.error(error_msg)
        raise PipelineAPIError(error_msg)

    except Exception as e:
        error_msg = f"Unexpected pipeline API error: {str(e)}"
        logger.error(error_msg)
        raise PipelineAPIError(error_msg)


def trigger_single_location_update(unmatched_location_id: int) -> dict:
    """
    Convenience method to trigger update for a single location.

    Args:
        unmatched_location_id: ID of the UnmatchedLocation that was just matched

    Returns:
        Dict with API response details
    """
    return trigger_location_updates([unmatched_location_id])


def is_pipeline_api_configured() -> bool:
    """
    Check if pipeline API is properly configured.

    Returns:
        True if API is configured, False otherwise
    """
    base_url = getattr(settings, "PIPELINE_API_BASE_URL", None)
    return bool(base_url and base_url.strip())


def get_pipeline_api_status() -> dict:
    """
    Check the status of the pipeline API.

    Returns:
        Dict with status information
    """
    if not is_pipeline_api_configured():
        return {"configured": False, "error": "Pipeline API not configured", "base_url": None}

    base_url = settings.PIPELINE_API_BASE_URL
    timeout = getattr(settings, "PIPELINE_API_TIMEOUT", 30)

    # Try a simple ping to check if API is available
    try:
        health_url = f"{base_url.rstrip('/')}/health/"
        response = requests.get(health_url, timeout=5)  # Short timeout for health check

        return {
            "configured": True,
            "available": response.status_code == 200,
            "base_url": base_url,
            "response_time": response.elapsed.total_seconds(),
            "status_code": response.status_code,
        }

    except requests.exceptions.RequestException as e:
        return {"configured": True, "available": False, "base_url": base_url, "error": str(e)}

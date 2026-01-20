"""API client for integrating with external alert dissemination systems."""

import logging

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class AlertAPIClient:
    """Client for publishing alerts to external systems."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: int = 30):
        """Initialize the API client.

        Args:
            base_url: Base URL for the alert API
            api_key: API authentication key
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set default headers
        self.session.headers.update({"Content-Type": "application/json", "User-Agent": "NRC-EWAS-Sudan-AlertFramework/1.0"})

        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def publish_alert(self, alert_data: dict) -> dict:
        """Publish an alert to the external API.

        Args:
            alert_data: Alert payload to send

        Returns:
            dict: Response from the API

        Raises:
            requests.RequestException: If the API request fails
        """
        url = f"{self.base_url}/alerts"

        try:
            logger.info(f"Publishing alert to {url}")
            response = self.session.post(url, json=alert_data, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Alert published successfully: {result.get('id', 'unknown')}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to publish alert: {e}")
            raise

    def update_alert(self, alert_id: str, alert_data: dict) -> dict:
        """Update an existing alert.

        Args:
            alert_id: ID of the alert to update
            alert_data: Updated alert payload

        Returns:
            dict: Response from the API
        """
        url = f"{self.base_url}/alerts/{alert_id}"

        try:
            logger.info(f"Updating alert {alert_id}")
            response = self.session.put(url, json=alert_data, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Alert updated successfully: {alert_id}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update alert {alert_id}: {e}")
            raise

    def cancel_alert(self, alert_id: str, reason: str = "Cancelled") -> dict:
        """Cancel an existing alert.

        Args:
            alert_id: ID of the alert to cancel
            reason: Reason for cancellation

        Returns:
            dict: Response from the API
        """
        url = f"{self.base_url}/alerts/{alert_id}/cancel"

        try:
            logger.info(f"Cancelling alert {alert_id}")
            response = self.session.post(url, json={"reason": reason}, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Alert cancelled successfully: {alert_id}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to cancel alert {alert_id}: {e}")
            raise

    def get_alert_status(self, alert_id: str) -> dict:
        """Get the status of a published alert.

        Args:
            alert_id: ID of the alert to check

        Returns:
            dict: Alert status information
        """
        url = f"{self.base_url}/alerts/{alert_id}/status"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get status for alert {alert_id}: {e}")
            raise

    def health_check(self) -> bool:
        """Check if the API is available.

        Returns:
            bool: True if API is healthy, False otherwise
        """
        url = f"{self.base_url}/health"

        try:
            response = self.session.get(url, timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False


class PublicAlertInterface:
    """Interface for managing alert publication to external systems."""

    def __init__(self):
        """Initialize the public alert interface."""
        self.clients = self._initialize_clients()

    def _initialize_clients(self) -> dict[str, AlertAPIClient]:
        """Initialize API clients from Django settings."""
        clients = {}

        # Get alert API configurations from settings
        alert_apis = getattr(settings, "ALERT_FRAMEWORK_APIS", {})

        for name, config in alert_apis.items():
            try:
                client = AlertAPIClient(base_url=config["base_url"], api_key=config.get("api_key"), timeout=config.get("timeout", 30))
                clients[name] = client
                logger.info(f"Initialized alert API client: {name}")
            except Exception as e:
                logger.error(f"Failed to initialize client {name}: {e}")

        return clients

    def format_alert_for_api(self, detection, template, language="en") -> dict:
        """Format a detection as an alert for external APIs.

        Args:
            detection: Detection object
            template: AlertTemplate object
            language: Language for alert content

        Returns:
            dict: Formatted alert payload
        """
        # Build context for template rendering
        locations = list(detection.locations.all())
        context = {
            "detection": detection,
            "detector_name": detection.detector.name,
            "detection_timestamp": detection.detection_timestamp,
            "confidence_score": detection.confidence_score,
            "locations": locations,
            "location_names": [loc.name for loc in locations],
            "primary_location": locations[0] if locations else None,
            "location": locations[0] if locations else None,
            "shock_type": detection.shock_type.name if detection.shock_type else None,
            "detection_data": detection.detection_data,
        }

        # Render alert content using template
        content = template.render(context)

        # Format locations
        locations = []
        for location in detection.locations.all():
            location_data = {"name": location.name, "coordinates": None}

            if hasattr(location, "name_ar"):
                location_data["name_ar"] = location.name_ar

            if location.latitude and location.longitude:
                location_data["coordinates"] = {"latitude": float(location.latitude), "longitude": float(location.longitude)}

            if location.admin_level:
                location_data["admin_level"] = {"name": location.admin_level.name, "code": location.admin_level.code}

            locations.append(location_data)

        # Create alert payload
        alert_payload = {
            "id": f"nrc-ewas-{detection.id}",
            "title": content.get("title", f"Alert from {detection.detector.name}"),
            "content": content.get("text", "Alert detected"),
            "language": language,
            "severity": self._map_confidence_to_severity(detection.confidence_score),
            "source": {"system": "NRC-EWAS-Sudan", "detector": detection.detector.name, "detector_type": detection.detector.class_name.split(".")[-1]},
            "timestamp": detection.detection_timestamp.isoformat(),
            "created_at": detection.created_at.isoformat(),
            "confidence_score": detection.confidence_score,
            "locations": locations,
            "metadata": {
                "detection_id": detection.id,
                "detector_id": detection.detector.id,
                "template_id": template.id,
                **detection.detection_data,
            },
        }

        return alert_payload

    def _map_confidence_to_severity(self, confidence_score: float) -> str:
        """Map confidence score to alert severity level.

        Args:
            confidence_score: Detection confidence (0.0-1.0)

        Returns:
            str: Severity level (low, medium, high, critical)
        """
        if confidence_score >= 0.9:
            return "critical"
        elif confidence_score >= 0.7:
            return "high"
        elif confidence_score >= 0.4:
            return "medium"
        else:
            return "low"

    def publish_alert(self, detection, template, target_apis: list | None = None, language="en") -> dict:
        """Publish an alert to external systems.

        Args:
            detection: Detection object to publish
            template: AlertTemplate to use for formatting
            target_apis: List of API names to publish to (None = all)
            language: Language for alert content

        Returns:
            dict: Publication results for each API
        """
        alert_payload = self.format_alert_for_api(detection, template, language)
        results = {}

        # Determine which APIs to publish to
        apis_to_use = target_apis or list(self.clients.keys())

        for api_name in apis_to_use:
            if api_name not in self.clients:
                results[api_name] = {"success": False, "error": f"API client {api_name} not configured"}
                continue

            client = self.clients[api_name]

            try:
                response = client.publish_alert(alert_payload)
                results[api_name] = {"success": True, "response": response, "external_id": response.get("id")}

                logger.info(f"Successfully published alert to {api_name}: {response.get('id')}")

            except Exception as e:
                results[api_name] = {"success": False, "error": str(e)}
                logger.error(f"Failed to publish alert to {api_name}: {e}")

        return results

    def update_alert(self, detection, template, external_ids: dict, language="en") -> dict:
        """Update an existing alert in external systems.

        Args:
            detection: Updated Detection object
            template: AlertTemplate to use for formatting
            external_ids: Mapping of API names to external alert IDs
            language: Language for alert content

        Returns:
            dict: Update results for each API
        """
        alert_payload = self.format_alert_for_api(detection, template, language)
        results = {}

        for api_name, external_id in external_ids.items():
            if api_name not in self.clients:
                results[api_name] = {"success": False, "error": f"API client {api_name} not configured"}
                continue

            client = self.clients[api_name]

            try:
                response = client.update_alert(external_id, alert_payload)
                results[api_name] = {"success": True, "response": response}

            except Exception as e:
                results[api_name] = {"success": False, "error": str(e)}
                logger.error(f"Failed to update alert in {api_name}: {e}")

        return results

    def cancel_alert(self, external_ids: dict, reason: str = "Alert cancelled") -> dict:
        """Cancel alerts in external systems.

        Args:
            external_ids: Mapping of API names to external alert IDs
            reason: Reason for cancellation

        Returns:
            dict: Cancellation results for each API
        """
        results = {}

        for api_name, external_id in external_ids.items():
            if api_name not in self.clients:
                results[api_name] = {"success": False, "error": f"API client {api_name} not configured"}
                continue

            client = self.clients[api_name]

            try:
                response = client.cancel_alert(external_id, reason)
                results[api_name] = {"success": True, "response": response}

            except Exception as e:
                results[api_name] = {"success": False, "error": str(e)}
                logger.error(f"Failed to cancel alert in {api_name}: {e}")

        return results

    def check_api_health(self) -> dict:
        """Check health status of all configured APIs.

        Returns:
            dict: Health status for each API
        """
        results = {}

        for api_name, client in self.clients.items():
            try:
                is_healthy = client.health_check()
                results[api_name] = {"healthy": is_healthy, "status": "OK" if is_healthy else "DOWN"}
            except Exception as e:
                results[api_name] = {"healthy": False, "status": "ERROR", "error": str(e)}

        return results

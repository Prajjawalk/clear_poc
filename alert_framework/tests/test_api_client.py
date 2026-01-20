"""Tests for API client and external alert integration."""

from unittest.mock import Mock, patch

import requests
from django.test import TestCase
from django.utils import timezone

from alert_framework.api_client import AlertAPIClient, PublicAlertInterface
from alert_framework.models import AlertTemplate, Detection, Detector
from alerts.models import ShockType


class AlertAPIClientTest(TestCase):
    """Test cases for AlertAPIClient."""

    def setUp(self):
        """Set up test data."""
        self.base_url = "https://api.example.com"
        self.api_key = "test_api_key_123"
        self.client = AlertAPIClient(base_url=self.base_url, api_key=self.api_key, timeout=30)

    def test_client_initialization(self):
        """Test client initialization with configuration."""
        self.assertEqual(self.client.base_url, self.base_url)
        self.assertEqual(self.client.api_key, self.api_key)
        self.assertEqual(self.client.timeout, 30)

        # Check headers
        self.assertEqual(self.client.session.headers["Authorization"], f"Bearer {self.api_key}")
        self.assertEqual(self.client.session.headers["Content-Type"], "application/json")

    def test_client_initialization_without_api_key(self):
        """Test client initialization without API key."""
        client = AlertAPIClient(base_url=self.base_url)

        self.assertNotIn("Authorization", client.session.headers)

    @patch("alert_framework.api_client.requests.Session.post")
    def test_publish_alert_success(self, mock_post):
        """Test successful alert publication."""
        # Mock successful response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"id": "alert_123", "status": "published", "created_at": "2023-01-01T12:00:00Z"}
        mock_post.return_value = mock_response

        alert_data = {"title": "Test Alert", "content": "This is a test alert", "severity": "high"}

        result = self.client.publish_alert(alert_data)

        self.assertEqual(result["id"], "alert_123")
        self.assertEqual(result["status"], "published")

        # Verify the request was made correctly
        mock_post.assert_called_once_with(f"{self.base_url}/alerts", json=alert_data, timeout=30)

    @patch("alert_framework.api_client.requests.Session.post")
    def test_publish_alert_failure(self, mock_post):
        """Test failed alert publication."""
        # Mock failed response
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.RequestException("API Error")
        mock_post.return_value = mock_response

        alert_data = {"title": "Test Alert"}

        with self.assertRaises(requests.RequestException):
            self.client.publish_alert(alert_data)

    @patch("alert_framework.api_client.requests.Session.put")
    def test_update_alert_success(self, mock_put):
        """Test successful alert update."""
        # Mock successful response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"id": "alert_123", "status": "updated", "updated_at": "2023-01-01T13:00:00Z"}
        mock_put.return_value = mock_response

        alert_id = "alert_123"
        alert_data = {"title": "Updated Alert"}

        result = self.client.update_alert(alert_id, alert_data)

        self.assertEqual(result["id"], "alert_123")
        self.assertEqual(result["status"], "updated")

        mock_put.assert_called_once_with(f"{self.base_url}/alerts/{alert_id}", json=alert_data, timeout=30)

    @patch("alert_framework.api_client.requests.Session.post")
    def test_cancel_alert_success(self, mock_post):
        """Test successful alert cancellation."""
        # Mock successful response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"id": "alert_123", "status": "cancelled", "reason": "False alarm"}
        mock_post.return_value = mock_response

        alert_id = "alert_123"
        reason = "False alarm"

        result = self.client.cancel_alert(alert_id, reason)

        self.assertEqual(result["status"], "cancelled")

        mock_post.assert_called_once_with(f"{self.base_url}/alerts/{alert_id}/cancel", json={"reason": reason}, timeout=30)

    @patch("alert_framework.api_client.requests.Session.get")
    def test_get_alert_status_success(self, mock_get):
        """Test successful alert status retrieval."""
        # Mock successful response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"id": "alert_123", "status": "active", "views": 1500, "last_updated": "2023-01-01T12:30:00Z"}
        mock_get.return_value = mock_response

        alert_id = "alert_123"
        result = self.client.get_alert_status(alert_id)

        self.assertEqual(result["status"], "active")
        self.assertEqual(result["views"], 1500)

        mock_get.assert_called_once_with(f"{self.base_url}/alerts/{alert_id}/status", timeout=30)

    @patch("alert_framework.api_client.requests.Session.get")
    def test_health_check_success(self, mock_get):
        """Test successful health check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        is_healthy = self.client.health_check()

        self.assertTrue(is_healthy)
        mock_get.assert_called_once_with(f"{self.base_url}/health", timeout=10)

    @patch("alert_framework.api_client.requests.Session.get")
    def test_health_check_failure(self, mock_get):
        """Test failed health check."""
        mock_get.side_effect = requests.RequestException("Connection failed")

        is_healthy = self.client.health_check()

        self.assertFalse(is_healthy)


class PublicAlertInterfaceTest(TestCase):
    """Test cases for PublicAlertInterface."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector")

        self.shock_type = ShockType.objects.create(name="Conflict")

        self.detection = Detection.objects.create(detector=self.detector, detection_timestamp=timezone.now(), confidence_score=0.85, shock_type=self.shock_type)

        self.template = AlertTemplate.objects.create(name="Test Template", shock_type=self.shock_type, title="Alert: {{ detector_name }}", text="Confidence: {{ confidence }}%")

    @patch("alert_framework.api_client.settings")
    def test_initialize_clients_from_settings(self, mock_settings):
        """Test client initialization from Django settings."""
        mock_settings.ALERT_FRAMEWORK_APIS = {"test_api": {"base_url": "https://api.example.com", "api_key": "test_key", "timeout": 45}}

        interface = PublicAlertInterface()

        self.assertIn("test_api", interface.clients)
        client = interface.clients["test_api"]
        self.assertEqual(client.base_url, "https://api.example.com")
        self.assertEqual(client.api_key, "test_key")
        self.assertEqual(client.timeout, 45)

    def test_map_confidence_to_severity(self):
        """Test confidence score to severity mapping."""
        interface = PublicAlertInterface()

        self.assertEqual(interface._map_confidence_to_severity(0.95), "critical")
        self.assertEqual(interface._map_confidence_to_severity(0.8), "high")
        self.assertEqual(interface._map_confidence_to_severity(0.6), "medium")
        self.assertEqual(interface._map_confidence_to_severity(0.3), "low")

    def test_format_alert_for_api(self):
        """Test alert formatting for API."""
        # Mock template render method
        with patch.object(self.template, 'render') as mock_render:
            mock_render.return_value = {"title": "Alert: Test Detector", "text": "Confidence: 85%"}

            interface = PublicAlertInterface()
            alert_payload = interface.format_alert_for_api(detection=self.detection, template=self.template, language="en")

            self.assertEqual(alert_payload["id"], f"nrc-ewas-{self.detection.id}")
            self.assertEqual(alert_payload["title"], "Alert: Test Detector")
            self.assertEqual(alert_payload["content"], "Confidence: 85%")
            self.assertEqual(alert_payload["language"], "en")
            self.assertEqual(alert_payload["severity"], "high")  # 0.85 confidence
            self.assertEqual(alert_payload["confidence_score"], 0.85)

            # Check source information
            self.assertEqual(alert_payload["source"]["system"], "NRC-EWAS-Sudan")
            self.assertEqual(alert_payload["source"]["detector"], "Test Detector")

            # Check metadata
            self.assertEqual(alert_payload["metadata"]["detection_id"], self.detection.id)
            self.assertEqual(alert_payload["metadata"]["detector_id"], self.detector.id)
            self.assertEqual(alert_payload["metadata"]["template_id"], self.template.id)

    @patch("alert_framework.api_client.PublicAlertInterface._initialize_clients")
    def test_publish_alert_success(self, mock_init_clients):
        """Test successful alert publication."""
        # Mock client
        mock_client = Mock()
        mock_client.publish_alert.return_value = {"id": "ext_123", "status": "published"}

        mock_init_clients.return_value = {"test_api": mock_client}

        interface = PublicAlertInterface()
        interface.clients = {"test_api": mock_client}

        with patch.object(interface, "format_alert_for_api") as mock_format:
            mock_format.return_value = {"title": "Test Alert"}

            results = interface.publish_alert(detection=self.detection, template=self.template, target_apis=["test_api"])

        self.assertIn("test_api", results)
        self.assertTrue(results["test_api"]["success"])
        self.assertEqual(results["test_api"]["external_id"], "ext_123")

    @patch("alert_framework.api_client.PublicAlertInterface._initialize_clients")
    def test_publish_alert_failure(self, mock_init_clients):
        """Test failed alert publication."""
        # Mock client that raises exception
        mock_client = Mock()
        mock_client.publish_alert.side_effect = Exception("API Error")

        mock_init_clients.return_value = {"test_api": mock_client}

        interface = PublicAlertInterface()
        interface.clients = {"test_api": mock_client}

        with patch.object(interface, "format_alert_for_api") as mock_format:
            mock_format.return_value = {"title": "Test Alert"}

            results = interface.publish_alert(detection=self.detection, template=self.template, target_apis=["test_api"])

        self.assertIn("test_api", results)
        self.assertFalse(results["test_api"]["success"])
        self.assertEqual(results["test_api"]["error"], "API Error")

    @patch("alert_framework.api_client.PublicAlertInterface._initialize_clients")
    def test_check_api_health(self, mock_init_clients):
        """Test API health checking."""
        # Mock clients with different health statuses
        mock_client_healthy = Mock()
        mock_client_healthy.health_check.return_value = True

        mock_client_unhealthy = Mock()
        mock_client_unhealthy.health_check.return_value = False

        mock_client_error = Mock()
        mock_client_error.health_check.side_effect = Exception("Connection failed")

        mock_init_clients.return_value = {"healthy_api": mock_client_healthy, "unhealthy_api": mock_client_unhealthy, "error_api": mock_client_error}

        interface = PublicAlertInterface()
        interface.clients = {"healthy_api": mock_client_healthy, "unhealthy_api": mock_client_unhealthy, "error_api": mock_client_error}

        results = interface.check_api_health()

        self.assertTrue(results["healthy_api"]["healthy"])
        self.assertEqual(results["healthy_api"]["status"], "OK")

        self.assertFalse(results["unhealthy_api"]["healthy"])
        self.assertEqual(results["unhealthy_api"]["status"], "DOWN")

        self.assertFalse(results["error_api"]["healthy"])
        self.assertEqual(results["error_api"]["status"], "ERROR")
        self.assertEqual(results["error_api"]["error"], "Connection failed")

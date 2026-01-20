"""Tests for LLM service views and API endpoints."""

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from llm_service.exceptions import RateLimitError, ValidationError


class LLMQueryViewTestCase(TestCase):
    """Test cases for LLMQueryView API endpoint."""

    def setUp(self):
        """Set up test client and data."""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        self.url = reverse("llm_service:api_query")

    def test_get_not_allowed(self):
        """Test that GET requests are not allowed."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    def test_missing_prompt(self):
        """Test request with missing prompt."""
        response = self.client.post(self.url, data=json.dumps({}), content_type="application/json")

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Missing required field: prompt", data["error"])

    def test_empty_prompt(self):
        """Test request with empty prompt."""
        response = self.client.post(self.url, data=json.dumps({"prompt": ""}), content_type="application/json")

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Prompt must be a non-empty string", data["error"])

    def test_invalid_json(self):
        """Test request with invalid JSON."""
        response = self.client.post(self.url, data="invalid json", content_type="application/json")

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Invalid JSON", data["error"])

    def test_invalid_temperature(self):
        """Test request with invalid temperature."""
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "prompt": "Hello",
                    "temperature": 1.5,  # Invalid: > 1
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Temperature must be between 0 and 1", data["error"])

    def test_invalid_max_tokens(self):
        """Test request with invalid max_tokens."""
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "prompt": "Hello",
                    "max_tokens": -10,  # Invalid: negative
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("max_tokens must be a positive integer", data["error"])

    @patch("llm_service.views.LLMService")
    def test_successful_regular_query(self, mock_service_class):
        """Test successful regular (non-streaming) query."""
        # Set up mock
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.query.return_value = "Hello! How can I help you?"
        mock_service.config = {"DEFAULT_PROVIDER": "litellm"}

        response = self.client.post(
            self.url,
            data=json.dumps({"prompt": "Tell me a joke", "provider": "litellm", "model": "gpt-3.5-turbo", "temperature": 0.7, "max_tokens": 150}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["response"], "Hello! How can I help you?")
        self.assertEqual(data["provider"], "litellm")
        self.assertEqual(data["model"], "gpt-3.5-turbo")
        self.assertIn("response_time_ms", data)

        # Verify service was called correctly
        mock_service.query.assert_called_once()

    @patch("llm_service.views.LLMService")
    def test_successful_streaming_query(self, mock_service_class):
        """Test successful streaming query."""
        # Set up mock
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.stream_query.return_value = iter(["Hello", " there", "!"])

        response = self.client.post(self.url, data=json.dumps({"prompt": "Hello", "stream": True}), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "text/plain")

        # Check response content (streaming)
        content = response.content.decode("utf-8")
        self.assertIn('{"chunk": "Hello"}', content)
        self.assertIn('{"chunk": " there"}', content)
        self.assertIn('{"chunk": "!"}', content)
        self.assertIn('{"done": true}', content)

    @patch("llm_service.views.LLMService")
    def test_rate_limit_error(self, mock_service_class):
        """Test rate limit error handling."""
        # Set up mock to raise RateLimitError
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.query.side_effect = RateLimitError("Rate limit exceeded")

        response = self.client.post(self.url, data=json.dumps({"prompt": "Hello"}), content_type="application/json")

        self.assertEqual(response.status_code, 429)
        data = response.json()
        self.assertEqual(data["error"], "Rate limit exceeded")

    @patch("llm_service.views.LLMService")
    def test_validation_error(self, mock_service_class):
        """Test validation error handling."""
        # Set up mock to raise ValidationError
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.query.side_effect = ValidationError("Invalid request")

        response = self.client.post(self.url, data=json.dumps({"prompt": "Hello"}), content_type="application/json")

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Validation error")

    @patch("llm_service.views.LLMService")
    def test_generic_service_error(self, mock_service_class):
        """Test generic service error handling."""
        # Set up mock to raise generic Exception
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.query.side_effect = Exception("Something went wrong")

        response = self.client.post(self.url, data=json.dumps({"prompt": "Hello"}), content_type="application/json")

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["error"], "Internal server error")

    def test_authenticated_user_query(self):
        """Test query with authenticated user."""
        self.client.login(username="testuser", password="testpass")

        with patch("llm_service.views.LLMService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.query.return_value = "Response for authenticated user"
            mock_service.config = {"DEFAULT_PROVIDER": "litellm"}

            response = self.client.post(self.url, data=json.dumps({"prompt": "Hello"}), content_type="application/json")

            self.assertEqual(response.status_code, 200)

            # Verify user was passed to service
            call_args = mock_service.query.call_args
            self.assertEqual(call_args.kwargs["user"], self.user)


class ProviderStatusViewTestCase(TestCase):
    """Test cases for provider status endpoint."""

    def setUp(self):
        """Set up test client."""
        self.client = Client()
        self.url = reverse("llm_service:api_provider_status")

    def test_post_not_allowed(self):
        """Test that POST requests are not allowed."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    @patch("llm_service.views.LLMService")
    def test_successful_provider_status(self, mock_service_class):
        """Test successful provider status retrieval."""
        # Set up mock
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_provider_status.return_value = {
            "providers": [{"name": "litellm", "active": True, "configured": True}, {"name": "openai", "active": False, "configured": False}]
        }

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("providers", data)
        self.assertEqual(len(data["providers"]), 2)
        self.assertEqual(data["providers"][0]["name"], "litellm")
        self.assertTrue(data["providers"][0]["active"])

    @patch("llm_service.views.LLMService")
    def test_provider_status_error(self, mock_service_class):
        """Test provider status error handling."""
        # Set up mock to raise exception
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_provider_status.side_effect = Exception("Status error")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["error"], "Failed to get provider status")


class ServiceStatsViewTestCase(TestCase):
    """Test cases for service statistics endpoint."""

    def setUp(self):
        """Set up test client and data."""
        self.client = Client()
        self.url = reverse("llm_service:api_service_stats")

        # Create some test data
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

    def test_post_not_allowed(self):
        """Test that POST requests are not allowed."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    @patch("llm_service.views.LLMService")
    def test_successful_service_stats(self, mock_service_class):
        """Test successful service statistics retrieval."""
        # Set up mock
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_service_stats.return_value = {"total_queries": 100, "successful_queries": 95, "avg_response_time_ms": 500, "cache": {"hit_rate": 0.3}}

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["total_queries"], 100)
        self.assertEqual(data["successful_queries"], 95)
        self.assertEqual(data["avg_response_time_ms"], 500)

    @patch("llm_service.views.LLMService")
    def test_service_stats_with_period_filter(self, mock_service_class):
        """Test service statistics with period filter."""
        # Set up mock
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_service_stats.return_value = {"total_queries": 50}

        response = self.client.get(self.url + "?period=week")

        self.assertEqual(response.status_code, 200)

        # Verify period was passed to service
        mock_service.get_service_stats.assert_called_once_with(period="week")

    @patch("llm_service.views.LLMService")
    def test_service_stats_error(self, mock_service_class):
        """Test service statistics error handling."""
        # Set up mock to raise exception
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_service_stats.side_effect = Exception("Stats error")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["error"], "Failed to get service stats")


class TestInterfaceViewTestCase(TestCase):
    """Test cases for test interface view."""

    def setUp(self):
        """Set up test client and user."""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        self.url = reverse("llm_service:test_interface")

    def test_requires_login(self):
        """Test that test interface requires authentication."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    @patch("llm_service.views.LLMService")
    def test_authenticated_access(self, mock_service_class):
        """Test authenticated access to test interface."""
        # Set up mock
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_provider_status.return_value = {"providers": [{"name": "litellm", "active": True}]}

        self.client.login(username="testuser", password="testpass")
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LLM Service Test Interface")
        self.assertContains(response, "Provider Status")

    @patch("llm_service.views.LLMService")
    def test_test_interface_provider_error(self, mock_service_class):
        """Test test interface with provider status error."""
        # Set up mock to raise exception
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_provider_status.side_effect = Exception("Provider error")

        self.client.login(username="testuser", password="testpass")
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        # Should still render page but with empty providers list
        self.assertContains(response, "LLM Service Test Interface")


class CSRFTestCase(TestCase):
    """Test CSRF handling for API endpoints."""

    def setUp(self):
        """Set up test client."""
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("llm_service:api_query")

    def test_csrf_exempt_for_api(self):
        """Test that API endpoints are CSRF exempt."""
        response = self.client.post(self.url, data=json.dumps({"prompt": "Hello"}), content_type="application/json")

        # Should not get CSRF error (403), but validation error (400) for missing auth
        self.assertNotEqual(response.status_code, 403)

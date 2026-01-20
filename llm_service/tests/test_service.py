"""Tests for LLM service core functionality."""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from llm_service.exceptions import ProviderNotFoundError, RateLimitError
from llm_service.models import CachedResponse, QueryLog
from llm_service.service import LLMService


class LLMServiceTestCase(TestCase):
    """Test cases for LLMService."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        self.test_config = {
            "DEFAULT_PROVIDER": "litellm",
            "PROVIDERS": {"litellm": {"API_BASE": "http://localhost:4000/v1", "API_KEY": "test-key", "MODEL": "gpt-3.5-turbo"}},
            "CACHE": {
                "ENABLED": True,
                "TTL_SECONDS": 3600,
                "USE_DATABASE": True,
                "USE_REDIS": False,  # Disable Redis for testing
            },
            "RATE_LIMITS": {
                "ENABLED": False  # Disable rate limiting for most tests
            },
        }

    @override_settings(LLM_SERVICE={})
    def test_service_initialization_with_defaults(self):
        """Test service initialization with default configuration."""
        service = LLMService()

        self.assertEqual(service.config["DEFAULT_PROVIDER"], "litellm")
        self.assertTrue(service.config["CACHE"]["ENABLED"])
        self.assertTrue(service.config["RATE_LIMITS"]["ENABLED"])

    def test_service_initialization_with_custom_config(self):
        """Test service initialization with custom configuration."""
        service = LLMService(self.test_config)

        self.assertEqual(service.config["DEFAULT_PROVIDER"], "litellm")
        self.assertFalse(service.config["RATE_LIMITS"]["ENABLED"])

    @patch("llm_service.registry.get_registry")
    @patch("llm_service.providers.litellm.OpenAI")
    def test_successful_query(self, mock_openai_class, mock_get_registry):
        """Test successful LLM query."""
        # Set up mocks
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        mock_provider = MagicMock()
        mock_provider.query.return_value = "Hello! How can I help you today?"
        mock_registry.get_provider_instance.return_value = mock_provider

        # Create service and make query
        service = LLMService(self.test_config)
        response = service.query(prompt="Tell me a joke", provider="litellm", user=self.user)

        self.assertEqual(response, "Hello! How can I help you today?")

        # Verify provider was called correctly
        mock_provider.query.assert_called_once()
        call_args = mock_provider.query.call_args
        self.assertEqual(call_args[0][0], "Tell me a joke")  # prompt

        # Verify query was logged
        log_entry = QueryLog.objects.get(user=self.user)
        self.assertEqual(log_entry.provider, "litellm")
        self.assertTrue(log_entry.success)

    @patch("llm_service.registry.get_registry")
    def test_query_with_invalid_provider(self, mock_get_registry):
        """Test query with invalid provider."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get_provider_instance.side_effect = ProviderNotFoundError("Provider not found")

        service = LLMService(self.test_config)

        with self.assertRaises(ProviderNotFoundError):
            service.query(prompt="Hello", provider="invalid_provider")

    @patch("llm_service.registry.get_registry")
    @patch("llm_service.providers.litellm.OpenAI")
    def test_query_with_caching(self, mock_openai_class, mock_get_registry):
        """Test query with caching enabled."""
        # Set up mocks
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        mock_provider = MagicMock()
        mock_provider.query.return_value = "Cached response"
        mock_registry.get_provider_instance.return_value = mock_provider

        service = LLMService(self.test_config)

        # First query - should hit provider
        response1 = service.query(prompt="Tell me a joke", provider="litellm", cache=True)

        self.assertEqual(response1, "Cached response")
        self.assertEqual(mock_provider.query.call_count, 1)

        # Second identical query - should hit cache
        response2 = service.query(prompt="Tell me a joke", provider="litellm", cache=True)

        self.assertEqual(response2, "Cached response")
        # Provider should not be called again
        self.assertEqual(mock_provider.query.call_count, 1)

        # Verify cache entry exists
        cache_entries = CachedResponse.objects.all()
        self.assertEqual(cache_entries.count(), 1)

    @patch("llm_service.registry.get_registry")
    @patch("llm_service.providers.litellm.OpenAI")
    def test_query_cache_disabled(self, mock_openai_class, mock_get_registry):
        """Test query with caching disabled."""
        # Set up mocks
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        mock_provider = MagicMock()
        mock_provider.query.return_value = "Non-cached response"
        mock_registry.get_provider_instance.return_value = mock_provider

        service = LLMService(self.test_config)

        # Make query with cache disabled
        response = service.query(prompt="Tell me a joke", provider="litellm", cache=False)

        self.assertEqual(response, "Non-cached response")

        # Verify no cache entry was created
        cache_entries = CachedResponse.objects.all()
        self.assertEqual(cache_entries.count(), 0)

    @patch("llm_service.registry.get_registry")
    def test_streaming_query(self, mock_get_registry):
        """Test streaming query functionality."""
        # Set up mocks
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        mock_provider = MagicMock()
        mock_provider.stream_query.return_value = iter(["Hello", " there", "!"])
        mock_registry.get_provider_instance.return_value = mock_provider

        service = LLMService(self.test_config)

        # Test streaming query
        chunks = list(service.stream_query(prompt="Tell me a joke", provider="litellm", user=self.user))

        self.assertEqual(chunks, ["Hello", " there", "!"])

        # Verify provider was called correctly
        mock_provider.stream_query.assert_called_once()

        # Verify query was logged
        log_entry = QueryLog.objects.get(user=self.user)
        self.assertEqual(log_entry.provider, "litellm")
        self.assertTrue(log_entry.success)

    def test_rate_limiting_enabled(self):
        """Test rate limiting functionality."""
        rate_limit_config = self.test_config.copy()
        rate_limit_config["RATE_LIMITS"] = {
            "ENABLED": True,
            "GLOBAL_RPM": 1,  # Very low limit for testing
            "USER_RPM": 1,
            "TOKEN_DAILY_LIMIT": 1000,
            "WINDOW_SIZE": 60,
        }

        service = LLMService(rate_limit_config)

        # Mock the actual query to avoid provider issues
        with patch.object(service, "_execute_query") as mock_execute:
            mock_execute.return_value = "Rate limited response"

            # First query should succeed
            response1 = service.query(prompt="Hello", user=self.user)
            self.assertEqual(response1, "Rate limited response")

            # Second query should fail due to rate limit
            with self.assertRaises(RateLimitError):
                service.query(prompt="Hello again", user=self.user)

    @patch("llm_service.registry.get_registry")
    def test_get_provider_status(self, mock_get_registry):
        """Test getting provider status."""
        # Set up mock registry
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.list_providers.return_value = ["litellm", "openai"]

        mock_provider = MagicMock()
        mock_provider.get_info.return_value = {"name": "LiteLLM", "type": "litellm", "version": "1.0"}
        mock_registry.get_provider_instance.return_value = mock_provider

        service = LLMService(self.test_config)
        status = service.get_provider_status()

        self.assertIn("providers", status)
        self.assertEqual(len(status["providers"]), 2)

    def test_get_service_stats(self):
        """Test getting service statistics."""
        # Create some test data
        QueryLog.objects.create(provider="litellm", model="gpt-3.5-turbo", prompt_hash="test123", total_tokens=50, response_time_ms=500, success=True, user=self.user)

        QueryLog.objects.create(provider="litellm", model="gpt-3.5-turbo", prompt_hash="test456", total_tokens=75, response_time_ms=750, success=False, user=self.user)

        service = LLMService(self.test_config)
        stats = service.get_service_stats(period="day")

        self.assertEqual(stats["total_queries"], 2)
        self.assertEqual(stats["successful_queries"], 1)
        self.assertEqual(stats["total_tokens"], 125)

    def test_token_estimation(self):
        """Test token estimation functionality."""
        service = LLMService(self.test_config)

        # Test basic estimation
        tokens = service._estimate_request_tokens("Hello, world!")
        self.assertGreater(tokens, 0)
        self.assertIsInstance(tokens, int)

        # Test with system message
        tokens_with_system = service._estimate_request_tokens("Hello, world!", system="You are a helpful assistant.")
        self.assertGreater(tokens_with_system, tokens)

        # Test with max_tokens
        tokens_with_max = service._estimate_request_tokens("Hello, world!", max_tokens=100)
        self.assertGreaterEqual(tokens_with_max, 100)

    def test_query_logging_success(self):
        """Test query logging for successful requests."""
        service = LLMService(self.test_config)

        service._log_query(
            prompt="Test prompt",
            response="Test response",
            provider="litellm",
            model="gpt-3.5-turbo",
            user=self.user,
            application="test_app",
            response_time_ms=500,
            cache_hit=False,
            success=True,
        )

        log_entry = QueryLog.objects.get(user=self.user)
        self.assertEqual(log_entry.provider, "litellm")
        self.assertEqual(log_entry.model, "gpt-3.5-turbo")
        self.assertTrue(log_entry.success)
        self.assertEqual(log_entry.response_time_ms, 500)
        self.assertIsNone(log_entry.error_message)

    def test_query_logging_failure(self):
        """Test query logging for failed requests."""
        service = LLMService(self.test_config)

        service._log_query(
            prompt="Test prompt",
            response="",
            provider="litellm",
            model="gpt-3.5-turbo",
            user=self.user,
            application="test_app",
            response_time_ms=1000,
            cache_hit=False,
            success=False,
            error="Rate limit exceeded",
        )

        log_entry = QueryLog.objects.get(user=self.user)
        self.assertFalse(log_entry.success)
        self.assertEqual(log_entry.error_message, "Rate limit exceeded")

    def test_get_provider_config(self):
        """Test getting provider configuration."""
        service = LLMService(self.test_config)

        # Test existing provider
        config = service._get_provider_config("litellm")
        self.assertEqual(config["API_BASE"], "http://localhost:4000/v1")

        # Test non-existent provider
        with self.assertRaises(ProviderNotFoundError):
            service._get_provider_config("nonexistent")

    @patch("llm_service.registry.get_registry")
    @patch("llm_service.providers.litellm.OpenAI")
    def test_query_with_default_provider(self, mock_openai_class, mock_get_registry):
        """Test query using default provider."""
        # Set up mocks
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        mock_provider = MagicMock()
        mock_provider.query.return_value = "Default provider response"
        mock_registry.get_provider_instance.return_value = mock_provider

        service = LLMService(self.test_config)

        # Query without specifying provider (should use default)
        response = service.query(prompt="Hello")

        self.assertEqual(response, "Default provider response")

        # Verify default provider was used
        call_args = mock_registry.get_provider_instance.call_args
        self.assertEqual(call_args[0][0], "litellm")  # provider name

    @patch("llm_service.registry.get_registry")
    @patch("llm_service.providers.litellm.OpenAI")
    def test_query_error_handling(self, mock_openai_class, mock_get_registry):
        """Test query error handling and logging."""
        # Set up mocks to raise an exception
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        mock_provider = MagicMock()
        mock_provider.query.side_effect = Exception("Provider error")
        mock_registry.get_provider_instance.return_value = mock_provider

        service = LLMService(self.test_config)

        # Query should raise exception
        with self.assertRaises(Exception):
            service.query(prompt="Hello", user=self.user)

        # Verify error was logged
        log_entry = QueryLog.objects.get(user=self.user)
        self.assertFalse(log_entry.success)
        self.assertEqual(log_entry.error_message, "Provider error")

"""Tests for LLM providers."""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase

from llm_service.providers.base import BaseLLMProvider
from llm_service.providers.litellm import LiteLLMProvider
from llm_service.exceptions import ProviderConfigError, QueryError


class BaseLLMProviderTestCase(TestCase):
    """Test cases for BaseLLMProvider abstract class."""

    def test_cannot_instantiate_base_provider(self):
        """Test that BaseLLMProvider cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            BaseLLMProvider({})

    def test_subclass_must_implement_abstract_methods(self):
        """Test that subclasses must implement abstract methods."""

        class IncompleteProvider(BaseLLMProvider):
            pass

        with self.assertRaises(TypeError):
            IncompleteProvider({})

    def test_complete_subclass_can_be_instantiated(self):
        """Test that complete subclass can be instantiated."""

        class CompleteProvider(BaseLLMProvider):
            def query(self, prompt, **kwargs):
                return "test response"

            def stream_query(self, prompt, **kwargs):
                yield "test"
                yield " response"

            def validate_config(self):
                return True

            def get_info(self):
                return {"name": "test", "version": "1.0"}

        provider = CompleteProvider({})
        self.assertIsInstance(provider, BaseLLMProvider)


class LiteLLMProviderTestCase(TestCase):
    """Test cases for LiteLLMProvider."""

    def setUp(self):
        """Set up test configuration."""
        self.config = {
            "API_BASE": "http://localhost:4000/v1",
            "API_KEY": "test-key",
            "MODEL": "gpt-3.5-turbo",
            "TIMEOUT": 30
        }

    def test_provider_initialization(self):
        """Test LiteLLM provider initialization."""
        provider = LiteLLMProvider(self.config)

        self.assertEqual(provider.api_base, "http://localhost:4000/v1")
        self.assertEqual(provider.api_key, "test-key")
        self.assertEqual(provider.default_model, "gpt-3.5-turbo")
        self.assertEqual(provider.timeout, 30)

    def test_provider_initialization_with_defaults(self):
        """Test provider initialization with default values."""
        minimal_config = {"API_KEY": "test-key"}
        provider = LiteLLMProvider(minimal_config)

        self.assertEqual(provider.api_base, "http://localhost:4000/v1")
        self.assertEqual(provider.api_key, "test-key")
        self.assertEqual(provider.default_model, "gpt-3.5-turbo")
        self.assertEqual(provider.timeout, 30)

    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        provider = LiteLLMProvider(self.config)
        self.assertTrue(provider.validate_config())

    def test_validate_config_missing_api_key(self):
        """Test configuration validation with missing API key."""
        config = self.config.copy()
        del config["API_KEY"]

        with self.assertRaises(ProviderConfigError):
            LiteLLMProvider(config)

    def test_get_info(self):
        """Test getting provider information."""
        provider = LiteLLMProvider(self.config)
        info = provider.get_info()

        self.assertEqual(info["name"], "LiteLLM")
        self.assertEqual(info["type"], "litellm")
        self.assertEqual(info["api_base"], "http://localhost:4000/v1")
        self.assertEqual(info["default_model"], "gpt-3.5-turbo")

    @patch('llm_service.providers.litellm.OpenAI')
    def test_query_success(self, mock_openai_class):
        """Test successful query execution."""
        # Set up mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_client.chat.completions.create.return_value = mock_response

        # Test query
        provider = LiteLLMProvider(self.config)
        response = provider.query("Hello, world!")

        self.assertEqual(response, "Test response")
        mock_client.chat.completions.create.assert_called_once()

    @patch('llm_service.providers.litellm.OpenAI')
    def test_query_with_parameters(self, mock_openai_class):
        """Test query with additional parameters."""
        # Set up mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_client.chat.completions.create.return_value = mock_response

        # Test query with parameters
        provider = LiteLLMProvider(self.config)
        response = provider.query(
            "Hello, world!",
            model="gpt-4",
            temperature=0.5,
            max_tokens=100,
            system="You are a helpful assistant."
        )

        self.assertEqual(response, "Test response")

        # Check that the correct parameters were passed
        call_args = mock_client.chat.completions.create.call_args
        self.assertEqual(call_args.kwargs["model"], "gpt-4")
        self.assertEqual(call_args.kwargs["temperature"], 0.5)
        self.assertEqual(call_args.kwargs["max_tokens"], 100)

        # Check messages structure
        messages = call_args.kwargs["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "You are a helpful assistant.")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "Hello, world!")

    @patch('llm_service.providers.litellm.OpenAI')
    def test_query_api_error(self, mock_openai_class):
        """Test query with API error."""
        # Set up mock to raise exception
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        # Test query
        provider = LiteLLMProvider(self.config)

        with self.assertRaises(QueryError):
            provider.query("Hello, world!")

    @patch('llm_service.providers.litellm.OpenAI')
    def test_stream_query_success(self, mock_openai_class):
        """Test successful streaming query."""
        # Set up mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock streaming response
        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="!"))])
        ]
        mock_client.chat.completions.create.return_value = iter(mock_chunks)

        # Test streaming query
        provider = LiteLLMProvider(self.config)
        chunks = list(provider.stream_query("Hello, world!"))

        self.assertEqual(chunks, ["Hello", " world", "!"])
        mock_client.chat.completions.create.assert_called_once()

        # Verify stream parameter was set
        call_args = mock_client.chat.completions.create.call_args
        self.assertTrue(call_args.kwargs.get("stream", False))

    @patch('llm_service.providers.litellm.OpenAI')
    def test_stream_query_with_none_content(self, mock_openai_class):
        """Test streaming query handling None content in chunks."""
        # Set up mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock streaming response with some None content
        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=None))]),  # None content
            MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))])
        ]
        mock_client.chat.completions.create.return_value = iter(mock_chunks)

        # Test streaming query
        provider = LiteLLMProvider(self.config)
        chunks = list(provider.stream_query("Hello, world!"))

        # Should skip None content
        self.assertEqual(chunks, ["Hello", " world"])

    @patch('llm_service.providers.litellm.OpenAI')
    def test_stream_query_api_error(self, mock_openai_class):
        """Test streaming query with API error."""
        # Set up mock to raise exception
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("Streaming API Error")

        # Test streaming query
        provider = LiteLLMProvider(self.config)

        with self.assertRaises(QueryError):
            list(provider.stream_query("Hello, world!"))

    def test_estimate_tokens(self):
        """Test token estimation."""
        provider = LiteLLMProvider(self.config)

        # Test simple estimation
        tokens = provider.estimate_tokens("Hello, world!")
        self.assertGreater(tokens, 0)
        self.assertIsInstance(tokens, int)

    def test_estimate_tokens_with_system_message(self):
        """Test token estimation with system message."""
        provider = LiteLLMProvider(self.config)

        tokens_without_system = provider.estimate_tokens("Hello, world!")
        tokens_with_system = provider.estimate_tokens("Hello, world!", system="You are helpful.")

        # Should have more tokens with system message
        self.assertGreater(tokens_with_system, tokens_without_system)

    @patch('llm_service.providers.litellm.tiktoken')
    def test_estimate_tokens_with_tiktoken(self, mock_tiktoken):
        """Test token estimation using tiktoken when available."""
        # Set up mock
        mock_encoding = MagicMock()
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
        mock_tiktoken.encoding_for_model.return_value = mock_encoding

        provider = LiteLLMProvider(self.config)
        tokens = provider.estimate_tokens("Hello, world!", model="gpt-3.5-turbo")

        self.assertEqual(tokens, 5)
        mock_tiktoken.encoding_for_model.assert_called_with("gpt-3.5-turbo")

    @patch('llm_service.providers.litellm.tiktoken')
    def test_estimate_tokens_tiktoken_fallback(self, mock_tiktoken):
        """Test token estimation fallback when tiktoken fails."""
        # Set up mock to raise exception
        mock_tiktoken.encoding_for_model.side_effect = Exception("Tiktoken error")

        provider = LiteLLMProvider(self.config)
        tokens = provider.estimate_tokens("Hello, world!", model="gpt-3.5-turbo")

        # Should fallback to simple estimation
        self.assertGreater(tokens, 0)
        self.assertIsInstance(tokens, int)

    def test_prepare_messages_user_only(self):
        """Test message preparation with user message only."""
        provider = LiteLLMProvider(self.config)
        messages = provider._prepare_messages("Hello, world!")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Hello, world!")

    def test_prepare_messages_with_system(self):
        """Test message preparation with system message."""
        provider = LiteLLMProvider(self.config)
        messages = provider._prepare_messages("Hello, world!", system="You are helpful.")

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "You are helpful.")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "Hello, world!")
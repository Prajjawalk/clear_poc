"""Management command to test LLM provider connectivity and functionality."""

import json
import time

from django.core.management.base import BaseCommand, CommandError

from llm_service.exceptions import ProviderNotFoundError, QueryError
from llm_service.service import LLMService


class Command(BaseCommand):
    help = "Test LLM provider connectivity and basic functionality"

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            type=str,
            help="Specific provider to test (tests all if not specified)",
        )
        parser.add_argument(
            "--model",
            type=str,
            help="Specific model to test",
        )
        parser.add_argument(
            "--prompt",
            type=str,
            default="Tell me a joke",
            help="Test prompt to send (default: 'Tell me a joke')",
        )
        parser.add_argument(
            "--streaming",
            action="store_true",
            help="Test streaming functionality",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output results in JSON format",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        try:
            # Initialize service
            service = LLMService()

            # Determine which providers to test
            if options["provider"]:
                providers_to_test = [options["provider"]]
            else:
                providers_to_test = service.registry.list_providers()

            if not providers_to_test:
                raise CommandError("No providers available to test")

            results = []

            for provider_name in providers_to_test:
                if options["json"]:
                    result = self._test_provider_json(service, provider_name, options)
                    results.append(result)
                else:
                    self._test_provider_verbose(service, provider_name, options)

            # Output JSON results if requested
            if options["json"]:
                self.stdout.write(json.dumps(results, indent=2))

        except Exception as e:
            raise CommandError(f"Command failed: {e}")

    def _test_provider_verbose(self, service, provider_name, options):
        """Test provider with verbose output."""
        self.stdout.write(f"\n{self.style.HTTP_INFO('=' * 60)}")
        self.stdout.write(f"{self.style.HTTP_INFO(f'Testing Provider: {provider_name}')}")
        self.stdout.write(f"{self.style.HTTP_INFO('=' * 60)}")

        try:
            # Test provider status
            self._test_provider_status(service, provider_name)

            # Test basic query
            self._test_basic_query(service, provider_name, options)

            # Test streaming if requested
            if options["streaming"]:
                self._test_streaming_query(service, provider_name, options)

            self.stdout.write(f"{self.style.SUCCESS(f'✓ Provider {provider_name} passed all tests')}")

        except Exception as e:
            self.stdout.write(f"{self.style.ERROR(f'✗ Provider {provider_name} failed: {e}')}")

    def _test_provider_json(self, service, provider_name, options):
        """Test provider and return JSON result."""
        result = {"provider": provider_name, "status": "unknown", "tests": {}, "error": None}

        try:
            # Test provider status
            status_result = self._test_provider_status_silent(service, provider_name)
            result["tests"]["status"] = status_result

            # Test basic query
            query_result = self._test_basic_query_silent(service, provider_name, options)
            result["tests"]["basic_query"] = query_result

            # Test streaming if requested
            if options["streaming"]:
                stream_result = self._test_streaming_query_silent(service, provider_name, options)
                result["tests"]["streaming"] = stream_result

            # Determine overall status
            all_passed = all(test.get("success", False) for test in result["tests"].values())
            result["status"] = "passed" if all_passed else "failed"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def _test_provider_status(self, service, provider_name):
        """Test provider status with verbose output."""
        self.stdout.write(f"\n{self.style.WARNING('Testing provider status...')}")

        try:
            status = service.get_provider_status()
            provider_info = None

            for provider in status.get("providers", []):
                if provider.get("name") == provider_name:
                    provider_info = provider
                    break

            if not provider_info:
                raise ProviderNotFoundError(f"Provider {provider_name} not found in status")

            if not provider_info.get("active", False):
                raise QueryError(f"Provider {provider_name} is not active")

            self.stdout.write(f"  Provider configured: {provider_info.get('configured', False)}")
            self.stdout.write(f"  Provider active: {provider_info.get('active', False)}")
            self.stdout.write(f"  {self.style.SUCCESS('✓ Status check passed')}")

        except Exception as e:
            self.stdout.write(f"  {self.style.ERROR(f'✗ Status check failed: {e}')}")
            raise

    def _test_provider_status_silent(self, service, provider_name):
        """Test provider status silently and return result."""
        try:
            status = service.get_provider_status()
            provider_info = None

            for provider in status.get("providers", []):
                if provider.get("name") == provider_name:
                    provider_info = provider
                    break

            if not provider_info:
                return {"success": False, "error": "Provider not found in status"}

            if not provider_info.get("active", False):
                return {"success": False, "error": "Provider not active"}

            return {"success": True, "configured": provider_info.get("configured", False), "active": provider_info.get("active", False)}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_basic_query(self, service, provider_name, options):
        """Test basic query with verbose output."""
        self.stdout.write(f"\n{self.style.WARNING('Testing basic query...')}")

        prompt = options["prompt"]
        model = options.get("model")

        try:
            self.stdout.write(f"  Prompt: {prompt}")
            self.stdout.write(f"  Provider: {provider_name}")
            if model:
                self.stdout.write(f"  Model: {model}")

            start_time = time.time()
            response = service.query(
                prompt=prompt,
                provider=provider_name,
                model=model,
                cache=False,  # Don't use cache for testing
            )
            response_time = time.time() - start_time

            self.stdout.write(f"  Response time: {response_time:.2f}s")
            self.stdout.write(f"  Response length: {len(response)} characters")
            self.stdout.write(f"  Response preview: {response[:100]}...")
            self.stdout.write(f"  {self.style.SUCCESS('✓ Basic query passed')}")

        except Exception as e:
            self.stdout.write(f"  {self.style.ERROR(f'✗ Basic query failed: {e}')}")
            raise

    def _test_basic_query_silent(self, service, provider_name, options):
        """Test basic query silently and return result."""
        try:
            prompt = options["prompt"]
            model = options.get("model")

            start_time = time.time()
            response = service.query(prompt=prompt, provider=provider_name, model=model, cache=False)
            response_time = time.time() - start_time

            return {"success": True, "response_time": response_time, "response_length": len(response), "response_preview": response[:100]}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_streaming_query(self, service, provider_name, options):
        """Test streaming query with verbose output."""
        self.stdout.write(f"\n{self.style.WARNING('Testing streaming query...')}")

        prompt = options["prompt"]
        model = options.get("model")

        try:
            self.stdout.write(f"  Prompt: {prompt}")
            self.stdout.write(f"  Provider: {provider_name}")
            if model:
                self.stdout.write(f"  Model: {model}")

            start_time = time.time()
            chunks = []

            for chunk in service.stream_query(prompt=prompt, provider=provider_name, model=model):
                chunks.append(chunk)
                # Show first few chunks
                if len(chunks) <= 3:
                    self.stdout.write(f"    Chunk {len(chunks)}: {chunk[:30]}...")

            response_time = time.time() - start_time
            full_response = "".join(chunks)

            self.stdout.write(f"  Total chunks: {len(chunks)}")
            self.stdout.write(f"  Response time: {response_time:.2f}s")
            self.stdout.write(f"  Total response length: {len(full_response)} characters")
            self.stdout.write(f"  {self.style.SUCCESS('✓ Streaming query passed')}")

        except Exception as e:
            self.stdout.write(f"  {self.style.ERROR(f'✗ Streaming query failed: {e}')}")
            raise

    def _test_streaming_query_silent(self, service, provider_name, options):
        """Test streaming query silently and return result."""
        try:
            prompt = options["prompt"]
            model = options.get("model")

            start_time = time.time()
            chunks = []

            for chunk in service.stream_query(prompt=prompt, provider=provider_name, model=model):
                chunks.append(chunk)

            response_time = time.time() - start_time
            full_response = "".join(chunks)

            return {"success": True, "chunk_count": len(chunks), "response_time": response_time, "response_length": len(full_response)}

        except Exception as e:
            return {"success": False, "error": str(e)}

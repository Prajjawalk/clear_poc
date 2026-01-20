"""Views for the LLM service API."""

import json
import logging
from typing import Any, Dict

from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from .exceptions import LLMServiceError, RateLimitError, ValidationError
from .service import LLMService

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class LLMQueryView(View):
    """API endpoint for LLM queries."""

    def __init__(self, **kwargs):
        """Initialize the view."""
        super().__init__(**kwargs)
        self.llm_service = LLMService()

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle POST requests for LLM queries.

        Expected JSON payload:
        {
            "prompt": "string",
            "provider": "string (optional)",
            "model": "string (optional)",
            "temperature": "float (optional, 0-1)",
            "max_tokens": "integer (optional)",
            "cache": "boolean (optional, default: true)",
            "stream": "boolean (optional, default: false)",
            "system": "string (optional)",
            "metadata": "object (optional)"
        }
        """
        try:
            # Parse request body
            data = json.loads(request.body)

            # Validate required fields
            if "prompt" not in data:
                return JsonResponse({"error": "Missing required field: prompt"}, status=400)

            prompt = data["prompt"]
            if not prompt or not isinstance(prompt, str):
                return JsonResponse({"error": "Prompt must be a non-empty string"}, status=400)

            # Extract parameters
            provider = data.get("provider")
            model = data.get("model")
            temperature = data.get("temperature")
            max_tokens = data.get("max_tokens")
            cache = data.get("cache", True)
            stream = data.get("stream", False)
            system = data.get("system")
            metadata = data.get("metadata", {})

            # Validate parameters
            if temperature is not None and (not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 1):
                return JsonResponse({"error": "Temperature must be between 0 and 1"}, status=400)

            if max_tokens is not None and (not isinstance(max_tokens, int) or max_tokens < 1):
                return JsonResponse({"error": "max_tokens must be a positive integer"}, status=400)

            # Build kwargs
            kwargs = {}
            if temperature is not None:
                kwargs["temperature"] = float(temperature)
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if system:
                kwargs["system"] = system

            # Handle streaming vs regular response
            if stream:
                return self._handle_streaming_query(request, prompt, provider, model, cache, **kwargs)
            else:
                return self._handle_regular_query(request, prompt, provider, model, cache, metadata, **kwargs)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
        except RateLimitError as e:
            return JsonResponse({"error": "Rate limit exceeded", "details": str(e)}, status=429)
        except ValidationError as e:
            return JsonResponse({"error": "Validation error", "details": str(e)}, status=400)
        except LLMServiceError as e:
            return JsonResponse({"error": "Service error", "details": str(e)}, status=500)
        except Exception as e:
            logger.error(f"Unexpected error in LLM query: {e}")
            return JsonResponse({"error": "Internal server error"}, status=500)

    def _handle_regular_query(
        self, request: HttpRequest, prompt: str, provider: str, model: str, cache: bool, metadata: Dict[str, Any], **kwargs
    ) -> JsonResponse:
        """Handle regular (non-streaming) query."""
        import time

        start_time = time.time()

        # Execute query
        response = self.llm_service.query(
            prompt=prompt, provider=provider, model=model, user=request.user if request.user.is_authenticated else None, cache=cache, **kwargs
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        # Return response
        return JsonResponse(
            {
                "response": response,
                "provider": provider or self.llm_service.config["DEFAULT_PROVIDER"],
                "model": model or "default",
                "response_time_ms": response_time_ms,
                "cache_hit": False,  # This would be determined in the service
                "metadata": metadata,
            }
        )

    def _handle_streaming_query(self, request: HttpRequest, prompt: str, provider: str, model: str, cache: bool, **kwargs) -> StreamingHttpResponse:
        """Handle streaming query."""

        def stream_generator():
            """Generator for streaming response."""
            try:
                for chunk in self.llm_service.stream_query(
                    prompt=prompt,
                    provider=provider,
                    model=model,
                    user=request.user if request.user.is_authenticated else None,
                    **kwargs,
                ):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"

                # Send completion marker
                yield f"data: {json.dumps({'done': True})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        response = StreamingHttpResponse(stream_generator(), content_type="text/plain")
        response["Cache-Control"] = "no-cache"
        return response


@require_http_methods(["GET"])
def provider_status(request: HttpRequest) -> JsonResponse:
    """Get status of all LLM providers."""
    try:
        service = LLMService()
        status = service.get_provider_status()
        return JsonResponse(status)

    except Exception as e:
        logger.error(f"Error getting provider status: {e}")
        return JsonResponse({"error": "Failed to get provider status"}, status=500)


@require_http_methods(["GET"])
def service_stats(request: HttpRequest) -> JsonResponse:
    """Get LLM service usage statistics."""
    try:
        period = request.GET.get("period", "day")
        provider_filter = request.GET.get("provider")
        application_filter = request.GET.get("application")

        service = LLMService()
        stats = service.get_service_stats(period=period)

        # Apply filters if specified
        if provider_filter or application_filter:
            # Additional filtering logic would be added here
            pass

        return JsonResponse(stats)

    except Exception as e:
        logger.error(f"Error getting service stats: {e}")
        return JsonResponse({"error": "Failed to get service stats"}, status=500)


@login_required
@require_http_methods(["GET"])
def dashboard(request: HttpRequest) -> HttpResponse:
    """Render the LLM service dashboard."""
    from django.shortcuts import render

    context = {
        "title": "LLM Service Dashboard",
    }

    try:
        service = LLMService()
        # Get basic stats for dashboard
        context["provider_status"] = service.get_provider_status()
        context["service_stats"] = service.get_service_stats(period="day")
    except Exception as e:
        logger.error(f"Error loading dashboard data: {e}")
        context["error"] = str(e)

    return render(request, "llm_service/dashboard.html", context)


@login_required
@require_http_methods(["GET"])
def test_interface(request: HttpRequest) -> HttpResponse:
    """Render the test interface for administrators."""
    from django.shortcuts import render

    context = {
        "title": "LLM Service Test Interface",
        "providers": [],  # Would be populated with available providers
    }

    try:
        service = LLMService()
        status = service.get_provider_status()
        context["providers"] = status.get("providers", [])
    except Exception as e:
        logger.error(f"Error loading providers for test interface: {e}")

    return render(request, "llm_service/test_interface.html", context)


@login_required
@require_http_methods(["GET"])
def query_logs(request: HttpRequest) -> HttpResponse:
    """Display query logs with filtering and pagination."""
    from django.shortcuts import render
    from django.core.paginator import Paginator
    from django.db.models import Q
    from .models import QueryLog

    # Get filter parameters
    search = request.GET.get('search', '')
    provider_filter = request.GET.get('provider', '')
    model_filter = request.GET.get('model', '')
    success_filter = request.GET.get('success', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Build query
    logs = QueryLog.objects.select_related('user').order_by('-created_at')

    if search:
        logs = logs.filter(
            Q(prompt_hash__icontains=search) |
            Q(error_message__icontains=search) |
            Q(application__icontains=search)
        )

    if provider_filter:
        logs = logs.filter(provider=provider_filter)

    if model_filter:
        logs = logs.filter(model=model_filter)

    if success_filter:
        if success_filter == 'true':
            logs = logs.filter(success=True)
        elif success_filter == 'false':
            logs = logs.filter(success=False)

    if date_from:
        logs = logs.filter(created_at__gte=date_from)

    if date_to:
        logs = logs.filter(created_at__lte=date_to)

    # Get unique providers and models for filters
    all_providers = QueryLog.objects.values_list('provider', flat=True).distinct()
    all_models = QueryLog.objects.values_list('model', flat=True).distinct().exclude(model__isnull=True)

    # Pagination
    paginator = Paginator(logs, 50)  # Show 50 logs per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Calculate statistics
    from django.db.models import Avg, Sum, Count
    stats = logs.aggregate(
        total_queries=Count('id'),
        success_count=Count('id', filter=Q(success=True)),
        avg_response_time=Avg('response_time_ms'),
        total_tokens_sum=Sum('total_tokens'),
        avg_tokens=Avg('total_tokens')
    )

    # Calculate success rate
    if stats['total_queries'] > 0:
        stats['success_rate'] = (stats['success_count'] / stats['total_queries']) * 100
    else:
        stats['success_rate'] = 0

    context = {
        "title": "Query Logs",
        "page_obj": page_obj,
        "stats": stats,
        "all_providers": all_providers,
        "all_models": all_models,
        "filters": {
            "search": search,
            "provider": provider_filter,
            "model": model_filter,
            "success": success_filter,
            "date_from": date_from,
            "date_to": date_to,
        }
    }

    return render(request, "llm_service/query_logs.html", context)
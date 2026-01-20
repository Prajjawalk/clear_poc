"""Views for translation app."""

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import translation
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import TranslationString
from .utils import get_translation_coverage, translate


@login_required
def translation_demo(request):
    """Demo page showing translation functionality."""
    # Get some sample translations for the demo
    sample_translations = TranslationString.objects.filter(is_active=True)[:5]

    # Create sample translations if none exist
    if not sample_translations.exists():
        sample_data = [
            ("welcome_message", "Welcome to our translation system!", "Main welcome message"),
            ("hello_user", "Hello, {name}!", "Greeting with user name parameter"),
            ("button_save", "Save", "Save button text"),
            ("error_required", "This field is required", "Required field error message"),
            ("footer_copyright", "© 2023 Your Company", "Footer copyright text"),
        ]

        for label, value, description in sample_data:
            TranslationString.objects.get_or_create(label=label, defaults={"value": value, "description": description, "is_active": True})

        sample_translations = TranslationString.objects.filter(is_active=True)[:5]

    context = {
        "sample_translations": sample_translations,
        "coverage": get_translation_coverage(),
    }

    return render(request, "translation/demo.html", context)


@login_required
def translation_coverage_view(request):
    """View showing translation coverage statistics."""
    coverage = get_translation_coverage()
    all_translations = TranslationString.objects.filter(is_active=True).order_by("label")

    context = {
        "coverage": coverage,
        "translations": all_translations,
    }

    return render(request, "translation/coverage.html", context)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_translate(request):
    """API endpoint for translating labels."""
    try:
        data = json.loads(request.body)
        label = data.get("label", "")
        kwargs = data.get("params", {})

        if not label:
            return JsonResponse({"error": "Label is required"}, status=400)

        result = translate(label, **kwargs)

        return JsonResponse(
            {
                "label": label,
                "translation": result,
                "params": kwargs,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["POST", "GET"])
def set_language(request):
    """
    Set the user's language preference.

    This view handles language switching from the language switcher component.
    It supports both AJAX and regular form submissions.
    """
    language_code = request.POST.get("language") or request.GET.get("language")
    next_url = request.POST.get("next") or request.GET.get("next") or "/"

    # Validate language code
    available_languages = [code for code, name in settings.LANGUAGES]
    if language_code and language_code in available_languages:
        # Activate the language for this request
        translation.activate(language_code)

        # Set language in session if available
        if hasattr(request, "session"):
            request.session[settings.LANGUAGE_SESSION_KEY] = language_code

        # Check if this is an AJAX request
        is_ajax = (
            request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest" or
            request.headers.get("Accept", "").startswith("application/json") or
            "ajax" in request.POST or
            "ajax" in request.GET
        )
        
        if is_ajax:
            # AJAX request - return JSON
            response = JsonResponse(
                {
                    "status": "success",
                    "language": language_code,
                    "next": next_url,
                }
            )
        else:
            # Regular form submission - redirect
            response = HttpResponseRedirect(next_url)

        # Set language cookie
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            language_code,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )

        return response

    # Invalid language code
    # Use same AJAX detection logic as above
    is_ajax = (
        request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest" or
        request.headers.get("Accept", "").startswith("application/json") or
        "ajax" in request.POST or
        "ajax" in request.GET
    )

    if is_ajax:
        return JsonResponse(
            {
                "status": "error",
                "message": f"Invalid language code: {language_code}",
                "available_languages": available_languages,
            },
            status=400,
        )
    else:
        # Redirect back with error (you might want to add a message framework message here)
        return HttpResponseRedirect(next_url)

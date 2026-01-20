"""Utility functions for translation app."""

import hashlib
import logging
import re

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, OperationalError
from django.utils import translation

logger = logging.getLogger(__name__)


def _sanitize_cache_key(key: str) -> str:
    """
    Sanitize cache key for memcached compatibility.

    Memcached has restrictions on cache keys:
    - Max length: 250 characters
    - Valid characters: A-Z, a-z, 0-9, and some special chars
    - No spaces, newlines, or control characters

    Args:
        key: Raw cache key

    Returns:
        Sanitized cache key safe for memcached
    """
    # Replace invalid characters with underscores
    sanitized = re.sub(r'[^\w\-\.]', '_', key)

    # If the key is too long, use a hash
    if len(sanitized) > 200:  # Leave room for prefixes
        # Keep the beginning and add a hash of the full key
        prefix = sanitized[:150]
        key_hash = hashlib.md5(key.encode('utf-8')).hexdigest()[:8]
        sanitized = f"{prefix}_{key_hash}"

    return sanitized


def translate(label: str, **kwargs) -> str:
    """
    Translate a label to the current language.

    This function provides robust fallback behavior:
    1. Try to get the translated string from the database
    2. If database is unavailable, return the label
    3. If label doesn't exist, return the label
    4. If translated value is empty, return the fallback or label
    5. Support parameter substitution with **kwargs

    Args:
        label: The unique identifier for the translation string
        **kwargs: Optional parameters for string formatting

    Returns:
        The translated string or the label as fallback
    """
    if not label:
        return ""

    # Clean label - remove whitespace
    label = label.strip()
    if not label:
        return ""

    # Generate cache key
    current_language = translation.get_language() or settings.LANGUAGE_CODE
    raw_cache_key = f"translation:{current_language}:{label}"
    cache_key = _sanitize_cache_key(raw_cache_key)

    # Try to get from cache first
    try:
        cached_value = cache.get(cache_key)
        if cached_value is not None:
            return _format_string(cached_value, **kwargs)
    except Exception as e:
        logger.warning(f"Cache error for translation '{label}': {e}")

    # Try to get from database
    try:
        from .models import TranslationString

        translation_obj = TranslationString.objects.filter(label=label, is_active=True).first()

        if translation_obj:
            # Get the translated value using django-modeltranslation
            value_field = f"value_{current_language}"
            translated_value = getattr(translation_obj, value_field, None)

            # Fallback to default language if translation is empty
            if not translated_value or not translated_value.strip():
                translated_value = translation_obj.value

            # Final fallback to label if still empty
            if not translated_value or not translated_value.strip():
                translated_value = label
            else:
                # Cache the successful translation
                try:
                    cache.set(cache_key, translated_value, timeout=3600)  # 1 hour
                except Exception as e:
                    logger.warning(f"Cache set error for translation '{label}': {e}")

            return _format_string(translated_value, **kwargs)

        else:
            # Translation not found - check if auto-creation is enabled
            auto_create = getattr(settings, "TRANSLATION_AUTO_CREATE_MISSING", False)
            if auto_create:
                try:
                    # Create new translation string with label as default value
                    TranslationString.objects.create(label=label, value=label, description=f"Auto-created translation for '{label}'", is_active=True)
                    logger.info(f"Auto-created translation string for label '{label}'")

                    # Cache the new translation
                    try:
                        cache.set(cache_key, label, timeout=3600)  # 1 hour
                    except Exception as e:
                        logger.warning(f"Cache set error for new translation '{label}': {e}")

                    return _format_string(label, **kwargs)

                except Exception as e:
                    logger.error(f"Error auto-creating translation '{label}': {e}")
                    # Continue to fallback

    except (DatabaseError, OperationalError) as e:
        logger.warning(f"Database error getting translation '{label}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting translation '{label}': {e}")

    # Final fallback: return the label itself
    return _format_string(label, **kwargs)


def _format_string(value: str, **kwargs) -> str:
    """
    Format a string with optional parameters.

    Args:
        value: The string to format
        **kwargs: Parameters for string formatting

    Returns:
        Formatted string
    """
    if not kwargs:
        return value

    try:
        return value.format(**kwargs)
    except (KeyError, ValueError) as e:
        logger.warning(f"String formatting error for '{value}': {e}")
        return value


def get_translation_coverage() -> dict:
    """
    Get translation coverage statistics.

    Returns:
        Dictionary with coverage information per language
    """
    try:
        from .models import TranslationString

        total_strings = TranslationString.objects.filter(is_active=True).count()
        if total_strings == 0:
            return {}

        coverage = {}
        for lang_code, lang_name in settings.LANGUAGES:
            if lang_code == settings.LANGUAGE_CODE:
                # Default language should always be 100%
                coverage[lang_code] = {
                    "name": lang_name,
                    "translated": total_strings,
                    "total": total_strings,
                    "percentage": 100.0,
                }
            else:
                value_field = f"value_{lang_code}"
                translated_count = TranslationString.objects.filter(is_active=True, **{f"{value_field}__isnull": False}).exclude(**{f"{value_field}__exact": ""}).count()

                coverage[lang_code] = {
                    "name": lang_name,
                    "translated": translated_count,
                    "total": total_strings,
                    "percentage": ((translated_count / total_strings) * 100 if total_strings > 0 else 0),
                }

        return coverage

    except Exception as e:
        logger.error(f"Error getting translation coverage: {e}")
        return {}


def clear_translation_cache(label: str | None = None) -> None:
    """
    Clear translation cache.

    Args:
        label: Optional specific label to clear. If None, clears all.
    """
    try:
        if label:
            # Clear specific label for all languages
            for lang_code, _ in settings.LANGUAGES:
                raw_cache_key = f"translation:{lang_code}:{label}"
                cache_key = _sanitize_cache_key(raw_cache_key)
                cache.delete(cache_key)
        else:
            # Clear all translation cache (this is a simple approach)
            # In production, you might want a more sophisticated cache invalidation
            from .models import TranslationString

            for obj in TranslationString.objects.filter(is_active=True):
                for lang_code, _ in settings.LANGUAGES:
                    raw_cache_key = f"translation:{lang_code}:{obj.label}"
                    cache_key = _sanitize_cache_key(raw_cache_key)
                    cache.delete(cache_key)

    except Exception as e:
        logger.warning(f"Error clearing translation cache: {e}")


def get_available_languages():
    """
    Get available languages with their names and codes.

    Returns:
        List of tuples (code, name) for available languages
    """
    return list(settings.LANGUAGES)


def get_current_language_info():
    """
    Get information about the current language.

    Returns:
        Dictionary with current language code, name, and direction
    """
    current_code = translation.get_language() or settings.LANGUAGE_CODE

    # Find the language name
    current_name = current_code
    for code, name in settings.LANGUAGES:
        if code == current_code:
            current_name = name
            break

    # Determine text direction (for RTL languages)
    rtl_languages = getattr(settings, "RTL_LANGUAGES", ["ar", "he", "fa", "ur"])
    is_rtl = current_code in rtl_languages

    return {
        "code": current_code,
        "name": current_name,
        "direction": "rtl" if is_rtl else "ltr",
        "is_rtl": is_rtl,
    }


def get_language_switch_url(language_code, current_path=None):
    """
    Generate URL for switching to a specific language.

    Args:
        language_code: The target language code
        current_path: Current URL path (optional)

    Returns:
        URL for language switching
    """
    from urllib.parse import urlencode

    from django.urls import reverse

    params = {"language": language_code}
    if current_path:
        params["next"] = current_path

    return f"{reverse('translation:set_language')}?{urlencode(params)}"


def is_language_available(language_code):
    """
    Check if a language code is available in the application.

    Args:
        language_code: The language code to check

    Returns:
        Boolean indicating if the language is available
    """
    available_codes = [code for code, name in settings.LANGUAGES]
    return language_code in available_codes


def get_auto_create_setting():
    """
    Get the current auto-create missing translations setting.

    Returns:
        Boolean indicating if auto-creation is enabled
    """
    return getattr(settings, "TRANSLATION_AUTO_CREATE_MISSING", False)


def set_auto_create_setting(enabled):
    """
    Set the auto-create missing translations setting.

    Args:
        enabled: Boolean to enable/disable auto-creation

    Note:
        This sets the runtime setting, but doesn't persist to settings file.
        For permanent changes, modify your Django settings.
    """
    settings.TRANSLATION_AUTO_CREATE_MISSING = enabled


def create_translation_string(label, value=None, description=None, is_active=True):
    """
    Manually create a translation string.

    Args:
        label: The unique identifier for the translation
        value: The translation value (defaults to label if not provided)
        description: Optional description for translators
        is_active: Whether the translation is active (default True)

    Returns:
        The created TranslationString object or None if creation failed
    """
    try:
        from .models import TranslationString

        if value is None:
            value = label

        if description is None:
            description = f"Translation for '{label}'"

        # Check if translation already exists
        existing = TranslationString.objects.filter(label=label).first()
        if existing:
            logger.warning(f"Translation string '{label}' already exists")
            return existing

        new_translation = TranslationString.objects.create(label=label, value=value, description=description, is_active=is_active)

        # Clear cache for this label
        clear_translation_cache(label)

        logger.info(f"Created translation string for label '{label}'")
        return new_translation

    except Exception as e:
        logger.error(f"Error creating translation string '{label}': {e}")
        return None

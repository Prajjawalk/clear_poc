"""Translation configuration for django-modeltranslation."""

from modeltranslation.translator import TranslationOptions, register

from .models import TranslationString


@register(TranslationString)
class TranslationStringTranslationOptions(TranslationOptions):
    """Translation options for TranslationString model."""

    fields = ("value", "description")
    required_languages = ("en",)
    fallback_languages = {"fr": ("en",), "es": ("en",)}

"""Translation configuration for location models."""

from modeltranslation.translator import TranslationOptions, translator

from .models import AdmLevel, Location


class AdmLevelTranslationOptions(TranslationOptions):
    """Translation options for AdmLevel model."""

    fields = ("name",)


class LocationTranslationOptions(TranslationOptions):
    """Translation options for Location model."""

    fields = ("name", "comment")


translator.register(AdmLevel, AdmLevelTranslationOptions)
translator.register(Location, LocationTranslationOptions)

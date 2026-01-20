"""Translation configuration for data pipeline models."""

from modeltranslation.translator import TranslationOptions, translator

from .models import Source, Variable


class SourceTranslationOptions(TranslationOptions):
    """Translation options for Source model."""

    fields = ("name", "description", "comment")


class VariableTranslationOptions(TranslationOptions):
    """Translation options for Variable model."""

    fields = ("name", "text")


translator.register(Source, SourceTranslationOptions)
translator.register(Variable, VariableTranslationOptions)

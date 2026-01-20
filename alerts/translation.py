"""Translation configuration for alerts app models."""

from modeltranslation.translator import TranslationOptions, register

from .models import Alert, EmailTemplate, ShockType


@register(ShockType)
class ShockTypeTranslationOptions(TranslationOptions):
    """Translation options for ShockType model."""

    fields = ("name",)


@register(Alert)
class AlertTranslationOptions(TranslationOptions):
    """Translation options for Alert model."""

    fields = ("title", "text")


@register(EmailTemplate)
class EmailTemplateTranslationOptions(TranslationOptions):
    """Translation options for EmailTemplate model."""

    fields = (
        "subject",
        "html_header",
        "html_footer",
        "html_wrapper",
        "text_header",
        "text_footer",
        "text_wrapper",
    )

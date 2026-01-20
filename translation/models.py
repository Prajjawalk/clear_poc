"""Models for translation app."""

from django.core.exceptions import ValidationError
from django.db import models


class TranslationString(models.Model):
    """Model to store translatable static strings for templates."""

    label = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique identifier for this translation string",
    )
    value = models.TextField(
        help_text="The text content to be translated",
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Context description for translators",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this translation string is active",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this translation was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this translation was last updated",
    )

    class Meta:
        """Meta configuration for TranslationString."""

        ordering = ["label"]
        verbose_name = "Translation String"
        verbose_name_plural = "Translation Strings"

    def __str__(self):
        """Return string representation."""
        return self.label

    def clean(self):
        """Validate the model."""
        super().clean()
        if not self.label.strip():
            raise ValidationError({"label": "Label cannot be empty or only whitespace."})
        if not self.value.strip():
            raise ValidationError({"value": "Value cannot be empty or only whitespace."})

"""Forms for alert framework components."""

import json

from django import forms
from django.core.exceptions import ValidationError

from alert_framework.models import Detector


class DetectorEditForm(forms.ModelForm):
    """Form for editing detector configuration."""

    configuration_json = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 10, "class": "form-control font-monospace", "placeholder": '{\n  "key": "value"\n}'}),
        label="Configuration (JSON)",
        help_text="Detector configuration in JSON format. Each detector type may have different configuration options.",
    )

    class Meta:
        """Meta configuration for DetectorEditForm."""

        model = Detector
        fields = ["name", "description", "active", "configuration_json"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        help_texts = {
            "name": "Display name for the detector",
            "description": "Detailed description of what this detector does",
            "active": "Whether this detector is currently active and can be executed",
        }

    def __init__(self, *args, **kwargs):
        """Initialize the form with configuration and styling."""
        super().__init__(*args, **kwargs)

        # Populate JSON field from configuration
        if self.instance and self.instance.configuration:
            self.fields["configuration_json"].initial = json.dumps(self.instance.configuration, indent=2, sort_keys=True)

        # Add CSS classes and help text
        for _field_name, field in self.fields.items():
            if hasattr(field.widget, "attrs"):
                field.widget.attrs["class"] = field.widget.attrs.get("class", "") + " form-control"

    def clean_configuration_json(self):
        """Validate that configuration is valid JSON."""
        json_text = self.cleaned_data["configuration_json"]

        if not json_text.strip():
            return {}

        try:
            config = json.loads(json_text)
            if not isinstance(config, dict):
                raise ValidationError("Configuration must be a JSON object (dictionary)")
            return config
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {str(e)}")

    def save(self, commit=True):
        """Save the detector with updated configuration."""
        detector = super().save(commit=False)
        detector.configuration = self.cleaned_data["configuration_json"]

        if commit:
            detector.save()

        return detector


class DetectorConfigurationHelpMixin:
    """Mixin to provide configuration help for different detector types."""

    DETECTOR_CONFIG_HELP = {
        "TestDetector": {
            "description": "Test detector for integration testing",
            "config_schema": {
                "test_source_name": "string - Name of test source to monitor",
                "minimum_confidence": "number (0-1) - Minimum confidence threshold for alerts",
                "disable_deduplication": "boolean - Whether to disable duplicate detection",
                "alert_threshold_multiplier": "number - Multiplier for alert thresholds",
            },
            "example": {"test_source_name": "Test Source", "minimum_confidence": 0.7, "disable_deduplication": True, "alert_threshold_multiplier": 1.0},
        },
        "ZScoreDetector": {
            "description": "Statistical anomaly detector using Z-score analysis",
            "config_schema": {
                "z_threshold": "number - Z-score threshold for anomaly detection",
                "window_size": "number - Size of rolling window for calculations",
                "min_samples": "number - Minimum samples required for analysis",
            },
            "example": {"z_threshold": 2.0, "window_size": 30, "min_samples": 10},
        },
    }

    @classmethod
    def get_config_help(cls, detector_class_name):
        """Get configuration help for a detector class."""
        return cls.DETECTOR_CONFIG_HELP.get(detector_class_name, {"description": "No specific configuration help available", "config_schema": {}, "example": {}})

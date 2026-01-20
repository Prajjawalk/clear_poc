"""Forms for data pipeline management."""

from django import forms
from django.core.exceptions import ValidationError

from .models import Source, Variable


class SourceForm(forms.ModelForm):
    """Form for creating and editing data sources."""

    class Meta:
        """Meta class for SourceForm."""

        model = Source
        fields = [
            "name",
            "description",
            "type",
            "info_url",
            "base_url",
            "class_name",
            "comment",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. ACLED, UNHCR, World Bank",
                }
            ),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Description of this data source and what it provides"}),
            "type": forms.Select(attrs={"class": "form-select"}),
            "info_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://example.com/about"}),
            "base_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://api.example.com/v1"}),
            "class_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "ACLEDSource"}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Any additional notes or configuration details"}),
        }
        help_texts = {
            "name": "Human-readable name for the data source",
            "description": "Brief description of what this source provides",
            "type": "Method used to retrieve data from this source",
            "info_url": "URL with documentation or information about this source",
            "base_url": "Base URL for API endpoints (for API sources)",
            "class_name": "Python class name that implements data retrieval for this source",
            "comment": "Internal notes about configuration, limitations, etc.",
        }

    def clean_class_name(self):
        """Validate class name format."""
        class_name = self.cleaned_data.get("class_name")
        if class_name:
            # Basic validation for Python class name format
            if not class_name.isidentifier():
                raise ValidationError("Class name must be a valid Python identifier")
            if not class_name[0].isupper():
                raise ValidationError("Class name should start with an uppercase letter")
        return class_name

    def clean(self):
        """Validate form data consistency."""
        cleaned_data = super().clean()
        source_type = cleaned_data.get("type")
        base_url = cleaned_data.get("base_url")

        # Require base_url for API and FTP sources
        if source_type in ["api", "ftp"] and not base_url:
            raise ValidationError({"base_url": f"Base URL is required for {source_type.upper()} sources"})

        return cleaned_data


class VariableForm(forms.ModelForm):
    """Form for creating and editing variables."""

    class Meta:
        """Meta class for VariableForm."""

        """Meta class for VariableForm."""
        model = Variable
        fields = ["source", "name", "code", "period", "adm_level", "type", "text"]
        widgets = {
            "source": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Fatalities, Refugee Count, GDP"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. fatalities, refugee_count, gdp"}),
            "period": forms.Select(attrs={"class": "form-select"}),
            "adm_level": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5}),
            "type": forms.Select(attrs={"class": "form-select"}),
            "text": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Detailed description of what this variable measures"}),
        }
        help_texts = {
            "source": "Select the data source this variable belongs to",
            "name": "Human-readable name for this variable",
            "code": "Unique code identifier (will be used in data processing)",
            "period": "How frequently this data is collected or updated",
            "adm_level": "Administrative level: 0=country, 1=state/province, 2=county/district, etc.",
            "type": "Type of data this variable contains",
            "text": "Detailed description, units of measurement, calculation methodology, etc.",
        }

    def __init__(self, *args, **kwargs):
        """Initialize VariableForm."""
        super().__init__(*args, **kwargs)
        # Order sources by name for better UX
        self.fields["source"].queryset = Source.objects.all().order_by("name")

        # Make source field more descriptive
        self.fields["source"].empty_label = "-- Select a Data Source --"

    def clean_code(self):
        """Validate variable code format."""
        code = self.cleaned_data.get("code")
        if code:
            # Convert to lowercase and replace spaces with underscores
            code = code.lower().replace(" ", "_")

            # Check if it's a valid identifier-like string
            import re

            if not re.match(r"^[a-z][a-z0-9_]*$", code):
                raise ValidationError("Code must start with a letter and contain only lowercase letters, numbers, and underscores")
        return code

    def clean(self):
        """Validate form data consistency."""
        cleaned_data = super().clean()
        source = cleaned_data.get("source")
        code = cleaned_data.get("code")

        # Check for unique code within source (excluding current instance)
        if source and code:
            existing = Variable.objects.filter(source=source, code=code)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)

            if existing.exists():
                raise ValidationError({"code": f'A variable with code "{code}" already exists for source "{source.name}"'})

        return cleaned_data


class VariableFilterForm(forms.Form):
    """Form for filtering variables in the list view."""

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Search variables..."}),
        label="Search",
    )

    source = forms.ModelChoiceField(
        queryset=Source.objects.all().order_by("name"),
        required=False,
        empty_label="All Sources",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    type = forms.ChoiceField(
        choices=[("", "All Types")] + Variable.TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Variable Type",
    )

    period = forms.ChoiceField(
        choices=[("", "All Periods")] + Variable.PERIOD_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class SourceFilterForm(forms.Form):
    """Form for filtering sources in the list view."""

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Search sources..."}),
        label="Search",
    )

    type = forms.ChoiceField(
        choices=[("", "All Types")] + Source.TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Source Type",
    )

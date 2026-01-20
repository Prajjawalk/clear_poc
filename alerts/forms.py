"""Forms for alerts app."""

from django import forms
from django.utils import timezone

from location.models import Location

from .models import Alert, ShockType, Subscription


class AlertForm(forms.ModelForm):
    """Form for creating alerts."""

    class Meta:
        model = Alert
        fields = ["title", "text", "shock_type", "data_source", "shock_date", "valid_from", "valid_until", "severity", "locations"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "text": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "shock_type": forms.Select(attrs={"class": "form-select"}),
            "data_source": forms.Select(attrs={"class": "form-select"}),
            "shock_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_from": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "valid_until": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "severity": forms.Select(attrs={"class": "form-select"}),
            "locations": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set severity choices without empty choice
        self.fields["severity"].choices = [(i, dict(Alert.SEVERITY_CHOICES)[i]) for i in range(1, 6)]

        # Ensure widget attrs are properly set (fix for widget inheritance issue)
        self.fields["shock_date"].widget.attrs.update({"type": "date"})

        # Set default values
        if not self.instance.pk:
            now = timezone.now()
            self.fields["shock_date"].initial = now.date()
            self.fields["valid_from"].initial = now
            self.fields["valid_until"].initial = now.replace(hour=23, minute=59, second=59) + timezone.timedelta(days=7)

        # Filter locations to admin1 level only
        self.fields["locations"].queryset = Location.objects.filter(admin_level__code="1")

        # Add help text
        self.fields["locations"].help_text = "Select the administrative regions affected by this alert"


class SubscriptionForm(forms.ModelForm):
    """Form for creating and editing subscriptions."""

    class Meta:
        model = Subscription
        fields = ["locations", "shock_types", "frequency", "method", "active"]
        widgets = {
            "locations": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "shock_types": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "frequency": forms.Select(attrs={"class": "form-select"}),
            "method": forms.Select(attrs={"class": "form-select"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter locations to admin1 level only
        self.fields["locations"].queryset = Location.objects.filter(admin_level__code="1")

        # Add help text
        self.fields["locations"].help_text = "Select the regions you want to receive alerts for"
        self.fields["shock_types"].help_text = "Select the types of alerts you want to receive"
        self.fields["frequency"].help_text = "Choose how often you want to receive alert notifications"
        self.fields["active"].help_text = "Uncheck to temporarily disable this subscription"


class AlertFeedbackForm(forms.Form):
    """Form for adding feedback comments to alerts."""

    comment = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Share your thoughts on this alert's accuracy or completeness..."}),
        max_length=1000,
        help_text="Maximum 1000 characters",
    )


class AlertFilterForm(forms.Form):
    """Form for filtering alerts in list view."""

    shock_type = forms.ModelChoiceField(queryset=ShockType.objects.all(), empty_label="All Types", required=False, widget=forms.Select(attrs={"class": "form-select"}))

    severity = forms.ChoiceField(choices=[("", "All Severities")] + Alert.SEVERITY_CHOICES, required=False, widget=forms.Select(attrs={"class": "form-select"}))

    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))

    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))

    search = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Search in title and content..."}))

    bookmarked = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ensure widget attrs are properly set (fix for widget inheritance issue)
        self.fields["date_from"].widget.attrs.update({"type": "date"})
        self.fields["date_to"].widget.attrs.update({"type": "date"})

"""Forms for location and gazetteer management."""

from django import forms
from django.contrib.gis import forms as geo_forms
from django.core.exceptions import ValidationError

from .models import AdmLevel, Gazetteer, Location


class FixedOSMWidget(geo_forms.OSMWidget):
    """OSMWidget with corrected Leaflet marker icon paths."""

    class Media:
        css = {
            'all': ('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',)
        }
        js = (
            'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
            'gis/js/OLMapWidget.js',  # Keep the Django widget functionality
        )

    def __init__(self, attrs=None):
        super().__init__(attrs)
        # Add the marker icon fix script
        if not hasattr(self, 'template_name'):
            self.template_name = 'gis/openlayers-osm.html'

    def render(self, name, value, attrs=None, renderer=None):
        # Get the base widget HTML
        widget_html = super().render(name, value, attrs, renderer)

        # Add Leaflet icon path fix
        icon_fix_script = """
        <script type="text/javascript">
        (function() {
            if (typeof L !== 'undefined' && L.Icon && L.Icon.Default) {
                // Delete the default icon URL method that tries to guess paths
                delete L.Icon.Default.prototype._getIconUrl;
                L.Icon.Default.mergeOptions({
                    iconUrl: '/static/leaflet/images/marker-icon.png',
                    iconRetinaUrl: '/static/leaflet/images/marker-icon-2x.png',
                    shadowUrl: '/static/leaflet/images/marker-shadow.png',
                    iconSize: [15, 25],         // Default is [25, 41] - making it 60% smaller
                    iconAnchor: [7, 25],        // Default is [12, 41] - adjusted proportionally
                    popupAnchor: [1, -22],      // Default is [1, -34] - adjusted proportionally
                    shadowSize: [25, 25],       // Default is [41, 41] - keeping shadow proportional
                    shadowAnchor: [6, 25]       // Default is [12, 41] - adjusted proportionally
                });
            }
        })();
        </script>
        """

        return widget_html + icon_fix_script


class LocationForm(forms.ModelForm):
    """Form for creating and editing locations."""

    class Meta:
        """Meta class for LocationForm."""

        model = Location
        fields = ["parent", "admin_level", "geo_id", "name", "boundary", "point", "comment"]
        widgets = {
            "parent": forms.Select(attrs={"class": "form-select"}),
            "admin_level": forms.Select(attrs={"class": "form-select"}),
            "geo_id": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., SD_001_002",
                }
            ),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Location name"}),
            "boundary": FixedOSMWidget(
                attrs={
                    "map_width": "100%",
                    "map_height": 400,
                    "default_zoom": 6,
                    "default_lat": 15.5527,
                    "default_lon": 32.5327,
                }
            ),
            "point": FixedOSMWidget(
                attrs={
                    "map_width": "100%",
                    "map_height": 300,
                    "default_zoom": 6,
                    "default_lat": 15.5527,
                    "default_lon": 32.5327,
                }
            ),
            "comment": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Additional information (optional)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """Initialize LocationForm."""
        super().__init__(*args, **kwargs)

        # Make fields required
        self.fields["admin_level"].required = True
        self.fields["geo_id"].required = True
        self.fields["name"].required = True

        # Set help texts
        self.fields["geo_id"].help_text = "Hierarchical geographic identifier (e.g., SD for Sudan, SD_001 for state, SD_001_002 for locality)"
        self.fields["parent"].help_text = "Parent location in the administrative hierarchy"
        self.fields["boundary"].help_text = "Geographic boundary polygon (optional)"
        self.fields["point"].help_text = "Representative point coordinates (optional)"

        # Filter parent choices based on admin level if instance exists
        if self.instance and self.instance.pk and hasattr(self.instance, 'admin_level') and self.instance.admin_level:
            parent_level_code = str(int(self.instance.admin_level.code) - 1) if int(self.instance.admin_level.code) > 0 else None
            if parent_level_code is not None:
                self.fields["parent"].queryset = Location.objects.filter(admin_level__code=parent_level_code).order_by("name")
            else:
                self.fields["parent"].queryset = Location.objects.none()
        else:
            # For new instances, show all potential parents (exclude lowest admin level)
            self.fields["parent"].queryset = Location.objects.exclude(admin_level__code='3').order_by("geo_id")

    def clean_geo_id(self):
        """Validate geo_id format and uniqueness."""
        geo_id = self.cleaned_data.get("geo_id", "").strip()

        if not geo_id:
            raise ValidationError("Geographic ID is required.")

        # Check for valid format (letters, numbers, underscores)
        if not geo_id.replace("_", "").replace("-", "").isalnum():
            raise ValidationError("Geographic ID can only contain letters, numbers, underscores, and hyphens.")

        # Check uniqueness
        queryset = Location.objects.filter(geo_id=geo_id)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise ValidationError("A location with this Geographic ID already exists.")

        return geo_id

    def clean(self):
        """Validate the relationship between parent, admin_level, and geo_id."""
        cleaned_data = super().clean()
        parent = cleaned_data.get("parent")
        admin_level = cleaned_data.get("admin_level")
        geo_id = cleaned_data.get("geo_id")

        if admin_level and parent:
            # Verify parent has correct admin level (one level higher)
            expected_parent_level = str(int(admin_level.code) - 1) if int(admin_level.code) > 0 else None
            if expected_parent_level and parent.admin_level.code != expected_parent_level:
                raise ValidationError({"parent": f"Parent must be at administrative level {expected_parent_level} ({AdmLevel.objects.get(code=expected_parent_level).name})"})

        # Level 0 (Country) should not have a parent
        if admin_level and admin_level.code == "0" and parent:
            raise ValidationError({"parent": "Country-level locations should not have a parent."})

        # Non-country levels should have a parent
        if admin_level and admin_level.code != "0" and not parent:
            raise ValidationError({"parent": "This administrative level requires a parent location."})

        # Validate geo_id hierarchy consistency
        if geo_id and parent:
            if not geo_id.startswith(parent.geo_id):
                raise ValidationError({"geo_id": f"Geographic ID should start with parent's geo_id '{parent.geo_id}'"})

        return cleaned_data


class GazetteerForm(forms.ModelForm):
    """Form for creating and editing gazetteer entries."""

    class Meta:
        """Meta class for GazetteerForm."""

        model = Gazetteer
        fields = ["location", "source", "code", "name"]
        widgets = {
            "location": forms.Select(attrs={"class": "form-select"}),
            "source": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., ACLED, UNHCR, local"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Alternative code (optional)"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Alternative name"}),
        }

    def __init__(self, *args, **kwargs):
        """Initialize GazetteerForm."""
        super().__init__(*args, **kwargs)

        # Set help texts
        self.fields["location"].help_text = "Select the location this entry refers to"
        self.fields["source"].help_text = "Data source identifier (e.g., ACLED, UNHCR, local)"
        self.fields["code"].help_text = "Alternative code used by the source (optional)"
        self.fields["name"].help_text = "Alternative name used by the source"

        # Order locations by geo_id for easier selection
        self.fields["location"].queryset = Location.objects.select_related("admin_level").order_by("geo_id")

    def clean(self):
        """Validate unique constraints."""
        cleaned_data = super().clean()
        location = cleaned_data.get("location")
        source = cleaned_data.get("source")
        code = cleaned_data.get("code")
        name = cleaned_data.get("name")

        if location and source and name:
            # Check unique constraint on location-source-name
            queryset = Gazetteer.objects.filter(location=location, source=source, name=name)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise ValidationError("This location-source-name combination already exists.")

        if location and source and code:
            # Check unique constraint on location-source-code
            queryset = Gazetteer.objects.filter(location=location, source=source, code=code)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise ValidationError("This location-source-code combination already exists.")

        return cleaned_data


class LocationSearchForm(forms.Form):
    """Form for searching and filtering locations."""

    search = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Search by name, geo ID, or comment..."},
        ),
    )

    admin_level = forms.ModelChoiceField(
        queryset=AdmLevel.objects.all().order_by("code"),
        required=False,
        empty_label="All levels",
        widget=forms.Select(
            attrs={"class": "form-select"},
        ),
    )

    parent = forms.ModelChoiceField(
        queryset=Location.objects.exclude(admin_level__code='3').order_by("geo_id"),
        required=False,
        empty_label="All parents",
        widget=forms.Select(
            attrs={"class": "form-select"},
        ),
    )


class LocationMatcherForm(forms.Form):
    """Form for location matching functionality."""

    location_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter location name to match..."}),
        help_text="Name of the location to find in the database",
    )

    source = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Source identifier (optional)"}),
        help_text="Source where this name comes from (e.g., ACLED, UNHCR)",
    )

    admin_level = forms.ModelChoiceField(
        queryset=AdmLevel.objects.all().order_by("code"),
        required=False,
        empty_label="Any level",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Expected administrative level of the location",
    )

    parent_id = forms.ModelChoiceField(
        queryset=Location.objects.exclude(admin_level__code='3').order_by("geo_id"),
        required=False,
        empty_label="No parent context",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Parent location to provide context for matching",
    )

"""Views for dashboard app."""

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max
from django.db.models.functions import Coalesce
from django.views.generic import TemplateView

from data_pipeline.models import VariableData
from .models import Theme


class DashboardMapView(LoginRequiredMixin, TemplateView):
    """Dashboard map view showing choropleth data layers."""

    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        """Add choropleth data and themes to context."""
        context = super().get_context_data(**kwargs)

        # Fetch themes and choropleth data from database
        themes = Theme.objects.filter(is_active=True).prefetch_related(
            'theme_variables__variable'
        )

        choropleth_data = self._get_choropleth_data_from_themes(themes)
        themes_config = self._get_themes_config(themes)

        context["choropleth_data_json"] = json.dumps(choropleth_data)
        context["themes_config_json"] = json.dumps(themes_config)
        context["themes"] = themes

        return context

    def _build_geojson_feature(self, geo_id, name, value, admin_level, start_date, end_date, boundary):
        """Build a single GeoJSON feature from location and value data."""
        return {
            'type': 'Feature',
            'id': geo_id,
            'properties': {
                'geo_id': geo_id,
                'name': name,
                'value': value,
                'admin_level': admin_level,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            },
            'geometry': json.loads(boundary.geojson)
        }

    def _get_themes_config(self, themes):
        """Build theme configuration for JavaScript."""
        themes_config = []

        for theme in themes:
            theme_variables = []
            for tv in theme.theme_variables.all():
                theme_variables.append({
                    'code': tv.variable.code,
                    'name': tv.variable.name,
                    'unit': tv.variable.unit,
                    'min_value': tv.min_value,
                    'max_value': tv.max_value,
                    'opacity': tv.opacity,
                })

            themes_config.append({
                'code': theme.code,
                'name': theme.name,
                'colormap': theme.colormap.get_colormap_config(),
                'colorbar_url': theme.colormap.get_colorbar_url(),
                'icon': theme.icon,
                'is_combined': theme.is_combined,
                'variables': theme_variables,
            })

        return themes_config

    def _get_choropleth_data_from_themes(self, themes):
        """Fetch latest data for all variables in active themes."""
        choropleth_layers = {}

        # Collect all unique variables from themes
        for theme in themes:
            theme_variables = theme.theme_variables.all()

            if not theme_variables:
                continue

            # Create one layer per variable
            for tv in theme_variables:
                layer = self._get_layer_data(
                    tv.variable.code,
                    tv.variable.name,
                    tv.variable.unit,
                    tv.variable.adm_level
                )
                if layer:
                    choropleth_layers[tv.variable.code] = layer

        return choropleth_layers

    def _get_layer_data(self, variable_code, name, unit, adm_level):
        """Fetch data for a single variable choropleth layer.

        Args:
            variable_code: The variable code to fetch data for
            name: Display name for the layer
            unit: Unit for the layer
            adm_level: Admin level for the layer (1 or 2)
        """
        from location.models import Location
        from django.db.models import OuterRef, Subquery

        # Get the latest end_date for this variable
        latest_date = VariableData.objects.filter(
            variable__code=variable_code
        ).aggregate(Max('end_date'))['end_date__max']

        if not latest_date:
            return None

        # Get all ADM2 locations
        all_adm2_locations = Location.objects.filter(
            admin_level__code='2',
            boundary__isnull=False
        )

        # Build features based on source admin level
        features = []

        if adm_level == 1:
            # For ADM1 data, distribute parent values to all ADM2 children
            parent_values = VariableData.objects.filter(
                variable__code=variable_code,
                end_date=latest_date,
                gid=OuterRef('parent_id')
            ).values('value')[:1]

            for location in all_adm2_locations.annotate(
                value=Coalesce(Subquery(parent_values), 0.0)
            ):
                features.append(
                    self._build_geojson_feature(
                        location.geo_id,
                        location.name,
                        location.value,
                        location.admin_level.code,
                        latest_date,
                        latest_date,
                        location.boundary
                    )
                )
        else:
            # For ADM2 data, left join directly
            location_values = VariableData.objects.filter(
                variable__code=variable_code,
                end_date=latest_date,
                gid=OuterRef('pk')
            ).values('value')[:1]

            for location in all_adm2_locations.annotate(
                value=Coalesce(Subquery(location_values), 0.0)
            ):
                features.append(
                    self._build_geojson_feature(
                        location.geo_id,
                        location.name,
                        location.value,
                        location.admin_level.code,
                        latest_date,
                        latest_date,
                        location.boundary
                    )
                )

        return {
            'name': name,
            'code': variable_code,
            'unit': unit,
            'adm_level': 2,  # Always return ADM2
            'latest_date': latest_date.isoformat(),
            'geojson': {
                'type': 'FeatureCollection',
                'features': features
            }
        }


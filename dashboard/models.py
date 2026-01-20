"""Dashboard models for configurable map themes and layers."""

from django.db import models
from django.core.exceptions import ValidationError

from data_pipeline.models import Variable
from django.utils import timezone


class ColorMap(models.Model):
    """Color map definition for choropleth layers.

    Can be either a named ColorBrewer scheme or a custom two-color linear scale.
    """

    NAMED_COLORMAPS = [
        ('Reds', 'Reds'),
        ('Blues', 'Blues'),
        ('Greens', 'Greens'),
        ('Oranges', 'Oranges'),
        ('Purples', 'Purples'),
        ('Greys', 'Greys'),
        ('YlOrRd', 'Yellow-Orange-Red'),
        ('YlOrBr', 'Yellow-Orange-Brown'),
        ('YlGnBu', 'Yellow-Green-Blue'),
        ('RdYlGn', 'Red-Yellow-Green'),
        ('Spectral', 'Spectral'),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name for this color map"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this color map"
    )

    # Named colormap option
    named_colormap = models.CharField(
        max_length=50,
        choices=NAMED_COLORMAPS,
        null=True,
        blank=True,
        help_text="Named ColorBrewer scheme (e.g., 'Reds', 'Blues')"
    )

    # Custom two-color scale option
    color_start = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        help_text="Starting color in hex format (e.g., '#ffffff')"
    )
    color_end = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        help_text="Ending color in hex format (e.g., '#ff0000')"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this color map is available for use"
    )

    colorbar_image = models.FileField(
        upload_to='colorbars/',
        null=True,
        blank=True,
        help_text="Custom colorbar image. If not provided, uses the default image from static/dashboard/images/"
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['name']
        verbose_name = 'Color Map'
        verbose_name_plural = 'Color Maps'

    def clean(self):
        """Validate that either named_colormap or both custom colors are provided."""
        has_named = bool(self.named_colormap)
        has_custom = bool(self.color_start and self.color_end)

        if not has_named and not has_custom:
            raise ValidationError(
                "Either specify a named colormap OR provide both start and end colors for a custom scale."
            )

        if has_named and has_custom:
            raise ValidationError(
                "Cannot specify both a named colormap and custom colors. Choose one."
            )

        if (self.color_start and not self.color_end) or (self.color_end and not self.color_start):
            raise ValidationError(
                "Both color_start and color_end must be provided for custom color scales."
            )

        # Validate hex color format
        if self.color_start and not self.color_start.startswith('#'):
            raise ValidationError("color_start must be in hex format (e.g., '#ffffff')")
        if self.color_end and not self.color_end.startswith('#'):
            raise ValidationError("color_end must be in hex format (e.g., '#ffffff')")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_colormap_config(self):
        """Return the colormap configuration for JavaScript."""
        if self.named_colormap:
            return {
                'type': 'named',
                'value': self.named_colormap
            }
        else:
            return {
                'type': 'custom',
                'value': [self.color_start, self.color_end]
            }

    def get_colorbar_url(self):
        """Return the URL for the colorbar image.

        Returns uploaded image URL if available, otherwise returns the default
        static image path based on the colormap name.
        """
        if self.colorbar_image:
            return self.colorbar_image.url

        # Generate default static path based on name
        # Convert colormap name to filename (e.g., 'Reds' -> 'reds.png')
        filename = f"{self.name.lower()}.png"
        return f"/static/dashboard/images/{filename}"

    def __str__(self):
        if self.named_colormap:
            return f"{self.name} ({self.named_colormap})"
        else:
            return f"{self.name} ({self.color_start} → {self.color_end})"


class Theme(models.Model):
    """Configurable map theme with associated variables and color scheme.

    Themes define groups of variables to display together on the dashboard map,
    with a shared color scheme for consistent visualization.
    """

    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier for this theme (e.g., 'combined_risk')"
    )
    name = models.CharField(
        max_length=255,
        help_text="Display name for this theme"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this theme represents"
    )
    colormap = models.ForeignKey(
        ColorMap,
        on_delete=models.PROTECT,
        related_name='themes',
        help_text="Color map to use for this theme"
    )
    icon = models.CharField(
        max_length=50,
        default='bi-stack',
        help_text="Bootstrap icon class (e.g., 'bi-stack', 'bi-droplet-fill')"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this theme is visible in the dashboard"
    )
    is_combined = models.BooleanField(
        default=False,
        help_text="If True, displays all variables as overlays with reduced opacity"
    )
    order = models.IntegerField(
        default=0,
        help_text="Display order in the dashboard (lower numbers first)"
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Dashboard Theme'
        verbose_name_plural = 'Dashboard Themes'

    def __str__(self):
        return self.name


class ThemeVariable(models.Model):
    """Association between a Theme and a Variable.

    Defines which variables belong to each theme and their specific
    visualization parameters.
    """

    theme = models.ForeignKey(
        Theme,
        on_delete=models.CASCADE,
        related_name='theme_variables'
    )
    variable = models.ForeignKey(
        Variable,
        on_delete=models.CASCADE,
        related_name='theme_associations'
    )
    order = models.IntegerField(
        default=0,
        help_text="Display order within the theme"
    )
    min_value = models.FloatField(
        null=True,
        blank=True,
        help_text="Minimum value for color scale domain (optional)"
    )
    max_value = models.FloatField(
        null=True,
        blank=True,
        help_text="Maximum value for color scale domain (optional)"
    )
    opacity = models.FloatField(
        default=0.7,
        help_text="Fill opacity for this variable (0.0 to 1.0)"
    )

    class Meta:
        ordering = ['order', 'variable__name']
        unique_together = ['theme', 'variable']
        verbose_name = 'Theme Variable'
        verbose_name_plural = 'Theme Variables'

    def __str__(self):
        return f"{self.theme.name} - {self.variable.name}"

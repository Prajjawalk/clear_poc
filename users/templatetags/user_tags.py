"""Template tags for user management."""

from django import template

register = template.Library()


@register.filter
def percentage(value, total):
    """Calculate percentage of value over total."""
    if not total:
        return 0
    try:
        return round((value / total) * 100, 1)
    except (TypeError, ZeroDivisionError):
        return 0
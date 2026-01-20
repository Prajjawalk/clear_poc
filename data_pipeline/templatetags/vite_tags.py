"""Template tags for Vite asset integration and data utilities."""

import json
import os
import html

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()


def _is_dev_mode():
    """Check if we're in development mode with Vite dev server."""
    return getattr(settings, "DEBUG", False)


def _get_vite_dev_server_url():
    """Get the Vite dev server URL from settings."""
    host = getattr(settings, "VITE_DEV_SERVER_HOST", "localhost")
    port = getattr(settings, "VITE_DEV_SERVER_PORT", 3000)
    return f"http://{host}:{port}"


def _get_manifest():
    """Load the Vite manifest file."""
    manifest_path = os.path.join(settings.BASE_DIR, "static", "dist", ".vite", "manifest.json")

    if not os.path.exists(manifest_path):
        return {}

    try:
        with open(manifest_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@register.simple_tag
def vite_asset(entry_name):
    """Get the URL for a Vite-compiled asset."""
    if _is_dev_mode():
        # In development, serve from Vite dev server
        return f"{_get_vite_dev_server_url()}/{entry_name}"

    manifest = _get_manifest()

    if entry_name in manifest:
        file_path = manifest[entry_name]["file"]
        return static(f"dist/{file_path}")

    # Fallback for development or if manifest not found
    return ""


@register.simple_tag
def vite_css(entry_name="scss/main.scss"):
    """Include CSS asset from Vite build."""
    if _is_dev_mode():
        # In development, Vite dev server handles CSS via JS imports
        return ""

    manifest = _get_manifest()

    if entry_name in manifest:
        file_path = manifest[entry_name]["file"]
        css_url = static(f"dist/{file_path}")
        return mark_safe(f'<link rel="stylesheet" href="{css_url}">')

    return ""


@register.simple_tag
def vite_js(entry_name="js/main.js"):
    """Include JavaScript asset from Vite build."""
    if _is_dev_mode():
        # In development, serve from Vite dev server with HMR
        # Vite root is './frontend' so paths are relative to that
        return mark_safe(f'<script type="module" src="{_get_vite_dev_server_url()}/{entry_name}"></script>')

    manifest = _get_manifest()

    if entry_name in manifest:
        file_path = manifest[entry_name]["file"]
        js_url = static(f"dist/{file_path}")
        return mark_safe(f'<script type="module" src="{js_url}"></script>')

    return ""


@register.simple_tag
def vite_legacy_js(entry_name="js/main.js"):
    """Include legacy JavaScript bundle for older browsers."""
    if _is_dev_mode():
        # No legacy bundle needed in development
        return ""

    manifest = _get_manifest()

    # Look for legacy version
    legacy_entry = entry_name.replace(".js", "-legacy.js")

    if legacy_entry in manifest:
        file_path = manifest[legacy_entry]["file"]
        js_url = static(f"dist/{file_path}")
        return mark_safe(f'<script nomodule src="{js_url}"></script>')

    return ""


@register.simple_tag
def vite_polyfills():
    """Include polyfills for legacy browsers."""
    if _is_dev_mode():
        # No polyfills needed in development
        return ""

    manifest = _get_manifest()

    polyfills_entry = "../vite/legacy-polyfills-legacy"

    if polyfills_entry in manifest:
        file_path = manifest[polyfills_entry]["file"]
        js_url = static(f"dist/{file_path}")
        return mark_safe(f'<script nomodule src="{js_url}"></script>')

    return ""


@register.simple_tag
def vite_hmr():
    """Include Vite HMR client for development."""
    if _is_dev_mode():
        return mark_safe(f'<script type="module" src="{_get_vite_dev_server_url()}/@vite/client"></script>')

    return ""


@register.filter
def json_escape(value):
    """Escape JSON data for safe use in HTML attributes."""
    if not value:
        return "{}"

    try:
        # If it's already a string, try to parse and reformat
        if isinstance(value, str):
            parsed = json.loads(value)
        else:
            parsed = value

        # Convert to JSON string and escape for HTML
        json_str = json.dumps(parsed, ensure_ascii=False)
        return html.escape(json_str)
    except (json.JSONDecodeError, TypeError):
        # If it's not valid JSON, just escape as string
        return html.escape(str(value))

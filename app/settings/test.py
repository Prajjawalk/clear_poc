"""Test-specific Django settings."""

from .core import *  # noqa: F403, F401

# Enable DEBUG to allow static file serving during E2E tests
DEBUG = True

# Force Vite to use built assets instead of dev server for E2E tests
DJANGO_VITE = {
    "default": {
        "dev_mode": False,  # Explicitly disable dev mode even with DEBUG=True
        "dev_server_host": "localhost",
        "dev_server_port": 3000,
        "static_url_prefix": "",  # Empty prefix since static/dist is in STATICFILES_DIRS
    }
}

# Fix static file serving for E2E tests
# Keep static/dist in STATICFILES_DIRS so Django can find and serve it with DEBUG=True
# This is already configured in core.py and inherited here

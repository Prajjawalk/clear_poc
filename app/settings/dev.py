"""Development environment specific settings."""

from .core import INSTALLED_APPS

# Dev-only apps
INSTALLED_APPS += ("django_extensions",)

# Enable debug toolbar, except when running tests
# if not TESTING:
#     INSTALLED_APPS += ("debug_toolbar",)
#     MIDDLEWARE += ("debug_toolbar.middleware.DebugToolbarMiddleware",)

INTERNAL_IPS = [
    "127.0.0.1",
]

# Debug Toolbar settings
# DEBUG_TOOLBAR_CONFIG = {
#     "SHOW_TOOLBAR_CALLBACK": "app.settings.dev.show_toolbar",
# }

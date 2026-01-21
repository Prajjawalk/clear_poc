"""
Django settings package for the project.

Uses split settings to organize settings across multiple files.
"""

from split_settings.tools import include, optional

from .core import *  # noqa
from .core import ENV

# Always include logging
include("logging.py")

# Only include dev settings in development mode
if ENV == "DEV":
    include(optional("dev.py"))

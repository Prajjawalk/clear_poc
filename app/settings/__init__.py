"""
Django settings package for the project.

Uses split settings to organize settings across multiple files.
"""

from split_settings.tools import include

from .core import *  # noqa

include(
    "dev.py",
    "logging.py",
)

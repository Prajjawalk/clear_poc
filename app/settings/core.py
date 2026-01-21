"""Django core settings."""

import json
import os
import sys
from os import environ
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # load environment variables

ENV = environ.get("DJANGO_ENV") or "DEV"
TESTING = "test" in sys.argv

if ENV == "DEV":
    DEBUG = True
else:
    DEBUG = False

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", default="django-insecure-4@#)7&!v3g1@8^2j5$%+0z6@*x@r9q3b1&=5!_8c4g0h3k6z7n")
_allowed_hosts_env = os.getenv("ALLOWED_HOSTS", "localhost")
# Support both JSON array and comma-separated formats
if _allowed_hosts_env.startswith("["):
    ALLOWED_HOSTS = json.loads(_allowed_hosts_env)
else:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(",") if h.strip()]

# Application definition
INSTALLED_APPS = [
    "modeltranslation",  # needs to be before django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.humanize",
    # add third-party apps here
    "django_vite",  # Vite integration
    "django_celery_beat",
    "django_celery_results",
    # add local apps here
    "app",  # main application
    "translation",  # custom static strings translation app
    "location",
    "task_monitoring",
    "data_pipeline",
    "alerts",
    "alert_framework",
    "llm_service",
    "users",  # user management app
    "notifications",  # internal notification system
    "dashboard",  # dashboard app
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "app.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

if TESTING:
    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.spatialite",
            "NAME": ":memory:",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.postgis",
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "NAME": os.getenv("DB_NAME", "nrc_ewas_sudan"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
        }
    }

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

USE_I18N = True
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("ar", "Arabic"),
]

TIME_ZONE = "UTC"

USE_TZ = True

# Language settings
LANGUAGE_SESSION_KEY = "django_language"
LANGUAGE_COOKIE_NAME = "django_language"
LANGUAGE_COOKIE_AGE = 31536000  # 1 year
LANGUAGE_COOKIE_PATH = "/"
LANGUAGE_COOKIE_DOMAIN = None
LANGUAGE_COOKIE_SECURE = False
LANGUAGE_COOKIE_HTTPONLY = False
LANGUAGE_COOKIE_SAMESITE = "Lax"

# Translation package settings
TRANSLATION_AUTO_CREATE_MISSING = True  # Automatically create missing translation strings


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static"
STATICFILES_DIRS = [
    BASE_DIR / "assets",
    BASE_DIR / "static" / "dist",  # Add Vite build output for development
]

# Media files (User uploads)
# https://docs.djangoproject.com/en/5.2/topics/files/

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Authentication Settings
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/auth/login/"

# Email Configuration
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

# SMTP Configuration (when using SMTP backend)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in ("true", "1", "yes")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() in ("true", "1", "yes")
EMAIL_DEFAULT_FROM = os.getenv("EMAIL_DEFAULT_FROM", "noreply@example.com")
DEFAULT_FROM_EMAIL = EMAIL_DEFAULT_FROM

# Celery Configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "django-db")
CELERY_CACHE_BACKEND = "django-cache"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Celery Beat performance optimization
CELERY_BEAT_SCHEDULE_FILENAME = "celerybeat-schedule"
CELERY_BEAT_SYNC_EVERY = 5  # Sync schedule every 5 beats instead of every beat
CELERY_BEAT_MAX_LOOP_INTERVAL = 60  # Max interval between beat iterations (seconds)

# Pipeline API Configuration for Location App
PIPELINE_API_BASE_URL = os.getenv("PIPELINE_API_BASE_URL", "http://localhost:8000/pipeline/api/")
PIPELINE_API_UPDATE_ENDPOINT = os.getenv("PIPELINE_API_UPDATE_ENDPOINT", "update-locations/")
PIPELINE_API_TIMEOUT = int(os.getenv("PIPELINE_API_TIMEOUT", "30"))  # seconds

# Site URL
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

# Slack Configuration
SLACK_ENABLED = os.getenv("SLACK_ENABLED", "False").lower() in ("true", "1", "yes")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_ALERT_CHANNEL = os.getenv("SLACK_ALERT_CHANNEL", "#alerts")

# LLM Service Configuration
# Note: Provider configurations are now stored in the database via ProviderConfig model
# Environment variables used:
#   - LITELLM_API_KEY: API key for LiteLLM proxy (required)
#   - LITELLM_API_BASE: Base URL for LiteLLM proxy (optional, defaults to http://localhost:4000)
LLM_SERVICE = {
    "LOG_CONTENT": True,  # Whether to log prompt and response text (set to False for privacy)
    "CACHE": {
        "ENABLED": True,
        "TTL_SECONDS": int(os.getenv("LLM_CACHE_TTL", "3600")),  # 1 hour
        "MAX_SIZE_MB": int(os.getenv("LLM_CACHE_MAX_SIZE_MB", "100")),
        "USE_DATABASE": True,
        "USE_REDIS": True,
    },
    "RATE_LIMITS": {
        "ENABLED": True,
        "GLOBAL_RPM": int(os.getenv("LLM_GLOBAL_RPM", "1000")),  # Global requests per minute
        "USER_RPM": int(os.getenv("LLM_USER_RPM", "100")),  # Per-user requests per minute
        "TOKEN_DAILY_LIMIT": int(os.getenv("LLM_TOKEN_DAILY_LIMIT", "1000000")),  # Daily token limit
        "WINDOW_SIZE": int(os.getenv("LLM_RATE_WINDOW_SIZE", "60")),  # Window size in seconds
    },
}

# Cache configuration for LLM service
if TESTING:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"),
            "KEY_PREFIX": "ewas",
            "TIMEOUT": 300,  # 5 minutes default
        }
    }

# Vite Configuration (django-vite)
DJANGO_VITE = {
    "default": {
        "dev_mode": DEBUG,
        "dev_server_host": os.getenv("VITE_DEV_SERVER_HOST", "localhost"),
        "dev_server_port": int(os.getenv("VITE_DEV_SERVER_PORT", "3000")),
        "static_url_prefix": "dist",
    }
}

# TiTiler Configuration
TITILER_BASE_URL = os.getenv("TITILER_BASE_URL", "http://127.0.0.1:8001")

# Import logging configuration

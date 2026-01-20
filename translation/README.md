# Django Translation

A comprehensive static string translation management system for Django applications with multi-language support, admin interface, and powerful template integration.

## Features

### **Translation Management**
- Database-backed static string translations
- Multi-language support via `django-modeltranslation`
- Robust fallback logic (missing → default language → label)
- Parameter substitution support (`"Hello {name}"`)
- Performance-optimized caching
- Auto-creation of missing translations (configurable)

### **Template Integration**
- Multiple template tags: `{% translate %}`, `{% trans %}`, `{{ label|t }}`
- Safe HTML rendering with `{% translate_safe %}`
- Variable resolution support
- Translation coverage reporting tags
- Language switching utilities

### **Language Switching**
- Multiple UI styles: dropdown, pills, flags, select, minimal
- AJAX and form-based switching
- Proper cookie and session handling
- Current language state management
- Flag images via external CDN

### **Admin Interface**
- Translation status indicators for all languages
- Bulk actions (activate, deactivate, clear cache)
- Preview functionality
- Cache invalidation on save/delete
- Integration with django-modeltranslation

### **Management Commands**
- `scan_translations`: Find translation strings in codebase
- `import_translations` / `export_translations`: JSON/CSV data exchange
- `prune_translations`: Remove empty translations
- `translation_stats`: Usage statistics and coverage reporting
- `auto_create_config`: Configure auto-creation settings

### 🔌 **API Endpoints**
- REST API for programmatic translation access
- Language switching endpoint
- AJAX-compatible responses

## Installation

```bash
uv add git+ssh://git@gitlab.com/MasaeAnalytics/common/django-packages/django-translation
```

## Quick Setup

### 1. Add to INSTALLED_APPS

** Important:** `modeltranslation` must be added **before** `django.contrib.admin`

```python
INSTALLED_APPS = [
    'modeltranslation',  # Must be before admin!
    'django.contrib.admin',
    'translation',
    # ... your other apps
]
```

### 2. Configure Languages

```python
LANGUAGES = [
    ('en', 'English'),
    ('fr', 'French'),
    ('es', 'Spanish'),
    ('de', 'German'),
    # Add your languages here
]

LANGUAGE_CODE = 'en'  # Default language
USE_I18N = True
```

### 3. Run Migrations

```bash
python manage.py migrate
```

### 4. Add URLs (Optional)

For demo interface and API endpoints:

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('translation/', include('translation.urls')),
    # ... your other URLs
]
```

## Usage

### In Templates

```html
{% load translation_tags %}

<!-- Basic translation -->
{% translate "Welcome to our site" %}

<!-- Translation with parameters -->
{% translate "Hello {name}" name=user.name %}

<!-- Safe HTML translation -->
{% translate_safe "Click <a href='/link/'>here</a>" %}

<!-- Using the filter -->
{{ "Contact Us"|t }}

<!-- Language switcher -->
{% language_switcher style="dropdown" %}
```

### In Python Code

```python
from translation.utils import translate as _

# Basic translation
message = _("Welcome to our site")

# Translation with parameters
greeting = _("Hello {name}", name="John")

# Translation with language override
french_msg = _("Welcome", language='fr')
```

### Management Commands

```bash
# Scan codebase for translation strings
python manage.py scan_translations

# Export translations to JSON
python manage.py export_translations --format json --output translations.json

# Import translations from CSV
python manage.py import_translations translations.csv

# View translation statistics
python manage.py translation_stats

# Remove empty translations
python manage.py prune_translations

# Configure auto-creation
python manage.py auto_create_config --enable
```

## Configuration Options

```python
# Optional settings
TRANSLATION_AUTO_CREATE_MISSING = False  # Auto-create missing translations
TRANSLATION_CACHE_TIMEOUT = 3600        # Cache timeout in seconds
TRANSLATION_DEFAULT_LANGUAGE = 'en'     # Fallback language
```

## Language Switcher Styles

The `{% language_switcher %}` tag supports multiple styles:

```html
<!-- Dropdown (default) -->
{% language_switcher style="dropdown" %}

<!-- Pills -->
{% language_switcher style="pills" %}

<!-- Flags -->
{% language_switcher style="flags" %}

<!-- Select box -->
{% language_switcher style="select" %}

<!-- Minimal links -->
{% language_switcher style="minimal" %}
```

## Admin Interface

1. Navigate to Django Admin → Translation → Translation strings
2. Add/edit translations with status indicators
3. Use bulk actions to manage multiple translations
4. Preview translations before publishing

## API Usage

### REST Endpoints

```bash
# Get all translations
GET /translation/api/translations/

# Get specific translation
GET /translation/api/translations/{id}/

# Create translation
POST /translation/api/translations/
{
    "label": "welcome_message",
    "context": "homepage"
}

# Update translation
PUT /translation/api/translations/{id}/
{
    "label": "welcome_message",
    "en": "Welcome!",
    "fr": "Bienvenue!"
}
```

### Language Switching API

```bash
# Switch language via AJAX
POST /translation/switch-language/
{
    "language": "fr"
}
```

## Development

### Running Tests

```bash
python manage.py test translation
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Requirements

- Python ≥ 3.8
- Django ≥ 4.0
- django-modeltranslation ≥ 0.18

## License

MIT License - see LICENSE file for details.

## Support

- **Documentation**:
- **Issues**: [GitHub Issues](https://gitlab.com/groups/MasaeAnalytics/common/django-packages/django-translation/-/issues)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and updates.

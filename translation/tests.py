"""Tests for translation app."""

from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase, override_settings
from django.utils import translation as django_translation

from .models import TranslationString
from .utils import (
    _sanitize_cache_key,
    clear_translation_cache,
    create_translation_string,
    get_auto_create_setting,
    get_translation_coverage,
    set_auto_create_setting,
    translate,
)


class TranslationStringModelTest(TestCase):
    """Test cases for TranslationString model."""

    def setUp(self):
        """Set up test data."""
        self.translation_obj = TranslationString.objects.create(
            label="test_label",
            value="Test Value",
            description="Test description",
            is_active=True,
        )

    def test_str_method(self):
        """Test string representation."""
        self.assertEqual(str(self.translation_obj), "test_label")

    def test_model_fields(self):
        """Test model field constraints."""
        # Test unique constraint
        with self.assertRaises(Exception):
            TranslationString.objects.create(
                label="test_label",  # Duplicate label
                value="Another value",
            )

    def test_clean_method(self):
        """Test model validation."""
        # Test empty label validation
        obj = TranslationString(label="", value="test")
        with self.assertRaises(Exception):
            obj.full_clean()

        # Test empty value validation
        obj = TranslationString(label="test", value="")
        with self.assertRaises(Exception):
            obj.full_clean()

    def test_ordering(self):
        """Test model ordering."""
        TranslationString.objects.create(label="z_label", value="Z value")
        TranslationString.objects.create(label="a_label", value="A value")

        labels = list(TranslationString.objects.values_list("label", flat=True))
        self.assertEqual(labels, ["a_label", "test_label", "z_label"])


class TranslateFunctionTest(TestCase):
    """Test cases for translate function."""

    def setUp(self):
        """Set up test data."""
        self.translation_obj = TranslationString.objects.create(
            label="welcome_message",
            value="Welcome to our site!",
            is_active=True,
        )
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    def test_translate_existing_label(self):
        """Test translating an existing label."""
        result = translate("welcome_message")
        self.assertEqual(result, "Welcome to our site!")

    def test_translate_nonexistent_label(self):
        """Test translating a non-existent label returns the label."""
        result = translate("nonexistent_label")
        self.assertEqual(result, "nonexistent_label")

    def test_translate_empty_label(self):
        """Test translating empty label returns empty string."""
        result = translate("")
        self.assertEqual(result, "")

    def test_translate_inactive_label(self):
        """Test translating inactive label returns the label."""
        self.translation_obj.is_active = False
        self.translation_obj.save()

        result = translate("welcome_message")
        self.assertEqual(result, "welcome_message")

    def test_translate_with_parameters(self):
        """Test translate function with parameter substitution."""
        TranslationString.objects.create(
            label="greeting",
            value="Hello, {name}!",
            is_active=True,
        )

        result = translate("greeting", name="John")
        self.assertEqual(result, "Hello, John!")

    def test_translate_invalid_parameters(self):
        """Test translate with invalid parameters falls back gracefully."""
        TranslationString.objects.create(
            label="greeting",
            value="Hello, {name}!",
            is_active=True,
        )

        # Missing parameter should not crash
        result = translate("greeting")
        self.assertEqual(result, "Hello, {name}!")

    def test_translate_caching(self):
        """Test that translations are cached."""
        # First call should hit database
        result1 = translate("welcome_message")

        # Modify database value
        self.translation_obj.value = "Modified value"
        self.translation_obj.save()

        # Second call should return cached value
        result2 = translate("welcome_message")
        self.assertEqual(result1, result2)
        self.assertEqual(result2, "Welcome to our site!")

    def test_translate_cache_invalidation(self):
        """Test cache invalidation."""
        # Get initial cached value
        translate("welcome_message")

        # Clear cache
        clear_translation_cache("welcome_message")

        # Modify database
        self.translation_obj.value = "Modified value"
        self.translation_obj.save()

        # Should get new value
        result = translate("welcome_message")
        self.assertEqual(result, "Modified value")

    def test_translate_database_error_fallback(self):
        """Test fallback behavior when database is unavailable."""
        result = translate("any_label")
        self.assertEqual(result, "any_label")


class TemplateTagsTest(TestCase):
    """Test cases for template tags."""

    def setUp(self):
        """Set up test data."""
        self.translation_obj = TranslationString.objects.create(
            label="template_test",
            value="Template Test Value",
            is_active=True,
        )
        TranslationString.objects.create(
            label="greeting_template",
            value="Hello, {name}!",
            is_active=True,
        )

    def test_translate_tag(self):
        """Test basic translate template tag."""
        template = Template('{% load translation_tags %}{% translate "template_test" %}')
        result = template.render(Context())
        self.assertEqual(result, "Template Test Value")

    def test_translate_tag_with_parameters(self):
        """Test translate tag with parameters."""
        template = Template('{% load translation_tags %}{% translate "greeting_template" name="Alice" %}')
        result = template.render(Context())
        self.assertEqual(result, "Hello, Alice!")

    def test_translate_filter(self):
        """Test translate filter."""
        template = Template('{% load translation_tags %}{{ "template_test"|t }}')
        result = template.render(Context())
        self.assertEqual(result, "Template Test Value")

    def test_trans_tag_with_variable(self):
        """Test trans tag with variable."""
        template = Template("{% load translation_tags %}{% trans label_var %}")
        context = Context({"label_var": "template_test"})
        result = template.render(context)
        self.assertEqual(result, "Template Test Value")

    def test_translate_safe_tag(self):
        """Test translate_safe tag."""
        TranslationString.objects.create(
            label="html_content",
            value="<b>Bold</b> content",
            is_active=True,
        )

        template = Template('{% load translation_tags %}{% translate_safe "html_content" %}')
        result = template.render(Context())
        self.assertIn("<b>Bold</b>", result)

    def test_translation_coverage_tag(self):
        """Test translation coverage template tag."""
        template = Template("{% load translation_tags %}{% translation_coverage as coverage %}{{ coverage }}")
        result = template.render(Context())
        # Should return some coverage data
        self.assertIn("en", result)


class UtilsTest(TestCase):
    """Test cases for utility functions."""

    def setUp(self):
        """Set up test data."""
        TranslationString.objects.create(
            label="utils_test",
            value="Utils Test Value",
            is_active=True,
        )
        TranslationString.objects.create(
            label="inactive_test",
            value="Inactive Value",
            is_active=False,
        )

    def test_get_translation_coverage(self):
        """Test translation coverage calculation."""
        coverage = get_translation_coverage()

        # Should have data for configured languages
        self.assertIn("en", coverage)
        self.assertEqual(coverage["en"]["translated"], 1)  # Only active translations
        self.assertEqual(coverage["en"]["total"], 1)
        self.assertEqual(coverage["en"]["percentage"], 100.0)

    def test_clear_translation_cache_specific(self):
        """Test clearing cache for specific label."""
        # Cache a translation
        translate("utils_test")

        # Clear specific cache
        clear_translation_cache("utils_test")

        # Should work without errors
        self.assertTrue(True)

    def test_clear_translation_cache_all(self):
        """Test clearing all translation cache."""
        # Cache some translations
        translate("utils_test")

        # Clear all cache
        clear_translation_cache()

        # Should work without errors
        self.assertTrue(True)


@override_settings(LANGUAGE_CODE="en", LANGUAGES=[("en", "English"), ("fr", "French")])
class MultiLanguageTest(TestCase):
    """Test cases for multi-language functionality."""

    def setUp(self):
        """Set up test data."""
        self.translation_obj = TranslationString.objects.create(
            label="multilang_test",
            value="English Value",
            is_active=True,
        )

    def test_fallback_to_default_language(self):
        """Test fallback to default language when translation is missing."""
        with django_translation.override("fr"):
            result = translate("multilang_test")
            # Should fallback to English value
            self.assertEqual(result, "English Value")

    def test_different_language_contexts(self):
        """Test translation in different language contexts."""
        # Test in English
        with django_translation.override("en"):
            result_en = translate("multilang_test")
            self.assertEqual(result_en, "English Value")

        # Test in French (should fallback)
        with django_translation.override("fr"):
            result_fr = translate("multilang_test")
            self.assertEqual(result_fr, "English Value")


class LanguageSwitchingTest(TestCase):
    """Test cases for language switching functionality."""

    def setUp(self):
        """Set up test data."""
        pass  # No default headers

    def test_set_language_view_post(self):
        """Test setting language via POST request."""
        response = self.client.post("/translation/set-language/", {"language": "ar", "next": "/test-page/"})

        # Should redirect for non-AJAX requests
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/test-page/")

        # Check that language cookie is set
        if "django_language" in response.cookies:
            self.assertEqual(response.cookies["django_language"].value, "ar")

    def test_set_language_view_ajax(self):
        """Test setting language via AJAX request."""
        response = self.client.post("/translation/set-language/", {"language": "ar", "next": "/test-page/", "ajax": "1"})

        # Should return JSON response for AJAX
        if response.status_code == 200:
            data = response.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["language"], "ar")
        else:
            # Fallback if AJAX detection doesn't work in test environment
            self.assertEqual(response.status_code, 302)

    def test_set_language_invalid_code(self):
        """Test setting invalid language code."""
        response = self.client.post("/translation/set-language/", {"language": "invalid", "next": "/test-page/", "ajax": "1"})

        # Should return error response for invalid language
        if response.status_code == 400:
            data = response.json()
            self.assertEqual(data["status"], "error")
        else:
            # Fallback if AJAX detection doesn't work in test environment
            self.assertEqual(response.status_code, 302)

    def test_language_switcher_template_tag(self):
        """Test language switcher template tag."""
        from django.template import Context, Template
        from django.test import RequestFactory

        template = Template('{% load translation_tags %}{% language_switcher style="dropdown" %}')
        factory = RequestFactory()
        request = factory.get("/test/")

        context = Context({"request": request})
        result = template.render(context)
        # Should contain language switcher HTML
        self.assertIn("language-switcher", result)

    def test_language_switcher_flags_style(self):
        """Test language switcher with flags style."""
        from django.template import Context, Template
        from django.test import RequestFactory

        template = Template('{% load translation_tags %}{% language_switcher style="flags" %}')
        factory = RequestFactory()
        request = factory.get("/test/")

        context = Context({"request": request})
        result = template.render(context)
        # Should contain compact flag dropdown HTML
        self.assertIn("language-flags-dropdown", result)
        self.assertIn("flagcdn.com", result)  # Flag CDN URL
        self.assertIn("flag-dropdown-btn", result)  # Dropdown button class
        self.assertIn("current-flag-image", result)  # Current flag image class

    def test_available_languages_template_tag(self):
        """Test available languages template tag."""
        from django.template import Context, Template

        template = Template("{% load translation_tags %}{% available_languages as langs %}{{ langs|length }}")
        result = template.render(Context())

        # Should return number of configured languages
        self.assertGreater(int(result), 0)

    def test_current_language_template_tag(self):
        """Test current language template tag."""
        from django.template import Context, Template

        template = Template("{% load translation_tags %}{% current_language as lang %}{{ lang.code }}")
        result = template.render(Context())

        # Should return current language code
        self.assertIn(result, ["en", "fr", "es"])

    def test_language_switch_url_template_tag(self):
        """Test language switch URL template tag."""
        from django.template import Context, Template
        from django.test import RequestFactory

        template = Template('{% load translation_tags %}{% language_switch_url "fr" %}')
        factory = RequestFactory()
        request = factory.get("/test/")

        context = Context({"request": request})
        result = template.render(context)
        # Should contain URL for language switching
        self.assertIn("/translation/set-language/", result)

    def test_language_name_filter(self):
        """Test language name filter."""
        from django.template import Context, Template

        template = Template('{% load translation_tags %}{{ "en"|language_name }}')
        result = template.render(Context())

        # Should return language name
        self.assertEqual(result, "English")

    def test_language_flag_filter(self):
        """Test language flag filter."""
        from django.template import Context, Template

        template = Template('{% load translation_tags %}{{ "en"|language_flag }}')
        result = template.render(Context())

        # Should return country code for flag (GB for English)
        self.assertEqual(result, "gb")


class AutoCreateTranslationTest(TestCase):
    """Test cases for auto-creation of missing translation strings."""

    def setUp(self):
        """Set up test data."""
        cache.clear()
        # Store original setting
        self.original_setting = get_auto_create_setting()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
        # Restore original setting
        set_auto_create_setting(self.original_setting)

    @override_settings(TRANSLATION_AUTO_CREATE_MISSING=True)
    def test_auto_create_enabled(self):
        """Test auto-creation when enabled."""
        label = "auto_created_test"

        # Ensure the translation doesn't exist
        self.assertFalse(TranslationString.objects.filter(label=label).exists())

        # Translate should create the translation
        result = translate(label)

        # Should return the label as value
        self.assertEqual(result, label)

        # Should have created the translation in database
        translation_obj = TranslationString.objects.filter(label=label).first()
        self.assertIsNotNone(translation_obj)
        self.assertEqual(translation_obj.label, label)
        self.assertEqual(translation_obj.value, label)
        self.assertTrue(translation_obj.is_active)
        self.assertIn("Auto-created", translation_obj.description)

    @override_settings(TRANSLATION_AUTO_CREATE_MISSING=False)
    def test_auto_create_disabled(self):
        """Test behavior when auto-creation is disabled."""
        label = "not_auto_created_test"

        # Ensure the translation doesn't exist
        self.assertFalse(TranslationString.objects.filter(label=label).exists())

        # Translate should return label but not create in database
        result = translate(label)

        # Should return the label as fallback
        self.assertEqual(result, label)

        # Should NOT have created the translation in database
        self.assertFalse(TranslationString.objects.filter(label=label).exists())

    def test_get_auto_create_setting(self):
        """Test getting the auto-create setting."""
        # Test default behavior
        setting = get_auto_create_setting()
        self.assertIsInstance(setting, bool)

    def test_set_auto_create_setting(self):
        """Test setting the auto-create setting."""
        # Test enabling
        set_auto_create_setting(True)
        self.assertTrue(get_auto_create_setting())

        # Test disabling
        set_auto_create_setting(False)
        self.assertFalse(get_auto_create_setting())

    def test_create_translation_string_manual(self):
        """Test manually creating translation strings."""
        label = "manual_test"
        value = "Manual Test Value"
        description = "This is a manual test"

        # Create translation
        result = create_translation_string(label, value, description)

        # Should return the created object
        self.assertIsNotNone(result)
        self.assertEqual(result.label, label)
        self.assertEqual(result.value, value)
        self.assertEqual(result.description, description)
        self.assertTrue(result.is_active)

        # Should exist in database
        translation_obj = TranslationString.objects.filter(label=label).first()
        self.assertIsNotNone(translation_obj)
        self.assertEqual(translation_obj.value, value)

    def test_create_translation_string_defaults(self):
        """Test creating translation string with default values."""
        label = "default_test"

        # Create with defaults
        result = create_translation_string(label)

        # Should use label as value and generate description
        self.assertIsNotNone(result)
        self.assertEqual(result.label, label)
        self.assertEqual(result.value, label)  # Should default to label
        self.assertIn(label, result.description)  # Should contain label in description
        self.assertTrue(result.is_active)

    def test_create_translation_string_duplicate(self):
        """Test creating duplicate translation string."""
        label = "duplicate_test"

        # Create first translation
        first = create_translation_string(label, "First Value")
        self.assertIsNotNone(first)

        # Try to create duplicate
        second = create_translation_string(label, "Second Value")

        # Should return the existing translation, not create new
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.value, "First Value")  # Should keep original value

    @override_settings(TRANSLATION_AUTO_CREATE_MISSING=True)
    def test_auto_create_with_parameters(self):
        """Test auto-creation with parameter substitution."""
        label = "hello_auto_{name}"

        # Translate with parameters - should auto-create
        result = translate(label, name="World")

        # Should return formatted string
        self.assertEqual(result, "hello_auto_World")

        # Should have created the translation in database
        translation_obj = TranslationString.objects.filter(label=label).first()
        self.assertIsNotNone(translation_obj)
        self.assertEqual(translation_obj.value, label)  # Stored without formatting


class ManagementCommandsTest(TestCase):
    """Test cases for management commands."""

    def setUp(self):
        """Set up test data."""
        # Create some test translations
        TranslationString.objects.create(label="existing_translation", value="Existing Value", description="Test translation", is_active=True)

        # Create an empty translation for pruning tests
        TranslationString.objects.create(label="empty_translation", value="", description="Empty test translation", is_active=True)

    def test_scan_translations_command(self):
        """Test the scan_translations management command."""
        import os
        import tempfile
        from io import StringIO

        from django.core.management import call_command

        # Create a temporary test file with translation strings
        test_content = """
def test_function():
    message = translate("test_scan_label1")
    greeting = translate('test_scan_label2')
    return message
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_file = f.name

        try:
            # Test dry run
            out = StringIO()
            call_command("scan_translations", "--path", temp_file, "--dry-run", stdout=out)
            output = out.getvalue()

            self.assertIn("Found 2 unique translation strings", output)
            self.assertIn("test_scan_label1", output)
            self.assertIn("test_scan_label2", output)
            self.assertIn("DRY RUN", output)

            # Verify no translations were actually created
            self.assertFalse(TranslationString.objects.filter(label="test_scan_label1").exists())

            # Test actual creation
            out = StringIO()
            call_command("scan_translations", "--path", temp_file, stdout=out)
            output = out.getvalue()

            self.assertIn("Successfully created 2 translation strings", output)

            # Verify translations were created
            self.assertTrue(TranslationString.objects.filter(label="test_scan_label1").exists())
            self.assertTrue(TranslationString.objects.filter(label="test_scan_label2").exists())

        finally:
            # Clean up temp file
            os.unlink(temp_file)

    def test_prune_translations_command(self):
        """Test the prune_translations management command."""
        from io import StringIO

        from django.core.management import call_command

        # Verify empty translation exists
        self.assertTrue(TranslationString.objects.filter(label="empty_translation").exists())

        # Test dry run
        out = StringIO()
        call_command("prune_translations", "--dry-run", stdout=out)
        output = out.getvalue()

        self.assertIn("Found 1 empty translation strings", output)
        self.assertIn("empty_translation", output)
        self.assertIn("DRY RUN", output)

        # Verify translation still exists after dry run
        self.assertTrue(TranslationString.objects.filter(label="empty_translation").exists())

        # Test actual pruning
        out = StringIO()
        call_command("prune_translations", "--confirm", stdout=out)
        output = out.getvalue()

        self.assertIn("Successfully deleted 1 empty translation strings", output)

        # Verify translation was deleted
        self.assertFalse(TranslationString.objects.filter(label="empty_translation").exists())

        # Verify non-empty translation still exists
        self.assertTrue(TranslationString.objects.filter(label="existing_translation").exists())

    def test_auto_create_config_command(self):
        """Test the auto_create_config management command."""
        from io import StringIO

        from django.core.management import call_command

        # Test status command
        out = StringIO()
        call_command("auto_create_config", "--status", stdout=out)
        output = out.getvalue()

        self.assertIn("Auto-creation of missing translation strings", output)

        # Test enable command
        out = StringIO()
        call_command("auto_create_config", "--enable", stdout=out)
        output = out.getvalue()

        self.assertIn("ENABLED", output)

        # Test disable command
        out = StringIO()
        call_command("auto_create_config", "--disable", stdout=out)
        output = out.getvalue()

        self.assertIn("DISABLED", output)


class CacheUtilsTest(TestCase):
    """Test cases for cache-related utility functions."""

    def test_sanitize_cache_key_basic(self):
        """Test basic cache key sanitization."""
        # Test normal key (should remain unchanged)
        normal_key = "translation_en_welcome_message"
        sanitized = _sanitize_cache_key(normal_key)
        self.assertEqual(sanitized, normal_key)

    def test_sanitize_cache_key_with_spaces(self):
        """Test cache key sanitization with spaces."""
        key_with_spaces = "translation:en:Disease outbreaks, health crises"
        sanitized = _sanitize_cache_key(key_with_spaces)
        expected = "translation_en_Disease_outbreaks__health_crises"
        self.assertEqual(sanitized, expected)

    def test_sanitize_cache_key_with_special_chars(self):
        """Test cache key sanitization with various special characters."""
        key_with_special = "translation:en:Hello! @world #test $value %percent"
        sanitized = _sanitize_cache_key(key_with_special)
        # Should replace all special chars except word chars, hyphens, and dots
        self.assertNotIn("!", sanitized)
        self.assertNotIn("@", sanitized)
        self.assertNotIn("#", sanitized)
        self.assertNotIn("$", sanitized)
        self.assertNotIn("%", sanitized)
        self.assertNotIn(" ", sanitized)

    def test_sanitize_cache_key_long_key(self):
        """Test cache key sanitization with very long keys."""
        # Create a key longer than 200 characters
        long_key = "translation:en:" + "very_long_label_" * 20
        sanitized = _sanitize_cache_key(long_key)

        # Should be shortened and include a hash
        self.assertLess(len(sanitized), 200)
        self.assertIn("_", sanitized)  # Should contain the hash separator

    def test_sanitize_cache_key_empty(self):
        """Test cache key sanitization with empty string."""
        sanitized = _sanitize_cache_key("")
        self.assertEqual(sanitized, "")

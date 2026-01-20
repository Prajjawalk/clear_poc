"""Django translation app configuration."""

from django.apps import AppConfig


class TranslationConfig(AppConfig):
    """Configuration for translation app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "translation"

    def ready(self):
        """Import translation configuration and register admin when app is ready."""
        # Import translation configuration first
        try:
            from . import translation  # noqa: F401
        except ImportError:
            pass

        # Register admin after translation configuration is loaded
        self._register_admin()

    def _register_admin(self):
        """Register admin interface with appropriate base class."""
        from django.contrib import admin

        from .admin import TranslationStringAdmin
        from .models import TranslationString

        try:
            from modeltranslation.admin import TranslationAdmin
            from modeltranslation.translator import translator

            # Check if model is registered for translation
            try:
                translator.get_options_for_model(TranslationString)

                # Model is registered, use TranslationAdmin
                class TranslationStringTranslationAdmin(TranslationAdmin, TranslationStringAdmin):
                    pass

                admin.site.register(TranslationString, TranslationStringTranslationAdmin)
            except Exception:
                # Model not registered or other error, use regular admin
                admin.site.register(TranslationString, TranslationStringAdmin)
        except ImportError:
            # modeltranslation not available, use regular admin
            admin.site.register(TranslationString, TranslationStringAdmin)

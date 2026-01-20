"""Management command to show translation statistics."""

from django.conf import settings
from django.core.management.base import BaseCommand

from ...models import TranslationString
from ...utils import get_translation_coverage


class Command(BaseCommand):
    """Show translation statistics and coverage."""

    help = "Display translation statistics and coverage information"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--detailed",
            action="store_true",
            help="Show detailed statistics per language",
        )
        parser.add_argument(
            "--missing",
            action="store_true",
            help="Show missing translations",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        self.show_overview()

        if options["detailed"]:
            self.show_detailed_coverage()

        if options["missing"]:
            self.show_missing_translations()

    def show_overview(self):
        """Show overview statistics."""
        total_strings = TranslationString.objects.count()
        active_strings = TranslationString.objects.filter(is_active=True).count()
        inactive_strings = total_strings - active_strings

        self.stdout.write(self.style.SUCCESS("Translation Overview"))
        self.stdout.write("=" * 50)
        self.stdout.write(f"Total strings:    {total_strings}")
        self.stdout.write(f"Active strings:   {active_strings}")
        self.stdout.write(f"Inactive strings: {inactive_strings}")
        self.stdout.write("")

    def show_detailed_coverage(self):
        """Show detailed coverage per language."""
        coverage = get_translation_coverage()

        self.stdout.write(self.style.SUCCESS("Coverage by Language"))
        self.stdout.write("=" * 50)

        for lang_code, info in coverage.items():
            percentage = info["percentage"]
            status_color = self.style.SUCCESS if percentage == 100 else (self.style.WARNING if percentage >= 50 else self.style.ERROR)

            self.stdout.write(f"{info['name']} ({lang_code}): {status_color(f'{percentage:.1f}%')} ({info['translated']}/{info['total']})")

        self.stdout.write("")

    def show_missing_translations(self):
        """Show missing translations for each language."""
        self.stdout.write(self.style.SUCCESS("Missing Translations"))
        self.stdout.write("=" * 50)

        active_strings = TranslationString.objects.filter(is_active=True)

        for lang_code, lang_name in settings.LANGUAGES:
            if lang_code == settings.LANGUAGE_CODE:
                continue  # Skip default language

            field_name = f"value_{lang_code}"
            missing_translations = active_strings.filter(**{f"{field_name}__isnull": True}) | active_strings.filter(**{f"{field_name}__exact": ""})

            if missing_translations.exists():
                self.stdout.write(f"\n{lang_name} ({lang_code}):")
                for obj in missing_translations:
                    self.stdout.write(f"  - {obj.label}")
            else:
                self.stdout.write(f"\n{lang_name} ({lang_code}): No missing translations")

        self.stdout.write("")

"""Management command to prune translation strings with no values in any language."""

from django.conf import settings
from django.core.management.base import BaseCommand

from ...models import TranslationString


class Command(BaseCommand):
    """Prune translation strings that have no values in any language."""

    help = "Remove translation strings that have no values in any configured language"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting it",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Also check inactive translations for pruning",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Skip confirmation prompt (use with caution)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed information about each translation checked",
        )

    def handle(self, *args, **options):
        """Handle the command."""
        dry_run = options["dry_run"]
        include_inactive = options["include_inactive"]
        confirm = options["confirm"]
        verbose = options["verbose"]

        # Get translations to check
        queryset = TranslationString.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)

        translations = queryset.order_by("label")

        if not translations.exists():
            self.stdout.write(self.style.WARNING("No translation strings found."))
            return

        self.stdout.write(f"Checking {translations.count()} translation strings...")
        self.stdout.write(f"Configured languages: {', '.join([code for code, name in settings.LANGUAGES])}")
        self.stdout.write("")

        # Find translations with no values
        empty_translations = []
        checked_count = 0

        for translation in translations:
            checked_count += 1
            if verbose and checked_count % 100 == 0:
                self.stdout.write(f"Checked {checked_count} translations...")

            has_value = self.translation_has_value(translation, verbose)

            if not has_value:
                empty_translations.append(translation)
                if verbose:
                    self.stdout.write(f"  - Empty: {translation.label}")

        # Report results
        if not empty_translations:
            self.stdout.write(self.style.SUCCESS("No empty translation strings found. All translations have values."))
            return

        self.stdout.write(f"\n{self.style.WARNING(f'Found {len(empty_translations)} empty translation strings:')}")

        for translation in empty_translations:
            status = "inactive" if not translation.is_active else "active"
            self.stdout.write(f"  - {translation.label} ({status})")

        if dry_run:
            self.stdout.write(f"\n{self.style.NOTICE('DRY RUN: Would delete the above empty translations.')}")
            return

        # Confirm deletion
        if not confirm:
            self.stdout.write(f"\n{self.style.WARNING('This will permanently delete the above translation strings.')}")
            response = input("Are you sure you want to continue? [y/N]: ")
            if response.lower() not in ["y", "yes"]:
                self.stdout.write("Operation cancelled.")
                return

        # Delete empty translations
        deleted_count = 0
        for translation in empty_translations:
            try:
                label = translation.label
                translation.delete()
                deleted_count += 1
                if verbose:
                    self.stdout.write(f"Deleted: {label}")
            except Exception as e:
                self.stderr.write(f'Error deleting translation "{translation.label}": {e}')

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully deleted {deleted_count} empty translation strings."))

    def translation_has_value(self, translation, verbose=False):
        """
        Check if a translation has any non-empty values in any language.

        Args:
            translation: TranslationString instance
            verbose: Whether to show detailed checking info

        Returns:
            Boolean indicating if translation has any values
        """
        # Check default value first
        if translation.value and translation.value.strip():
            if verbose:
                self.stdout.write(f"  ✓ {translation.label} has default value")
            return True

        # Check language-specific values
        for lang_code, lang_name in settings.LANGUAGES:
            if lang_code == settings.LANGUAGE_CODE:
                continue  # Already checked default above

            field_name = f"value_{lang_code}"

            # Check if the field exists (django-modeltranslation might not be configured)
            if hasattr(translation, field_name):
                value = getattr(translation, field_name, None)
                if value and value.strip():
                    if verbose:
                        self.stdout.write(f"  ✓ {translation.label} has {lang_name} value")
                    return True

        # No values found in any language
        if verbose:
            self.stdout.write(f"  ✗ {translation.label} has no values in any language")

        return False

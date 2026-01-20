"""Management command to import translations from JSON/CSV."""

import csv
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import TranslationString


class Command(BaseCommand):
    """Import translations from JSON or CSV format."""

    help = "Import translation strings from JSON or CSV format"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "file_path",
            type=str,
            help="Path to the import file",
        )
        parser.add_argument(
            "--format",
            choices=["json", "csv"],
            help="Import format (auto-detected if not specified)",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing translations (default: skip existing)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        file_path = options["file_path"]

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            raise CommandError(f"File not found: {file_path}")
        except Exception as e:
            raise CommandError(f"Error reading file: {e}")

        # Auto-detect format if not specified
        format_type = options["format"]
        if not format_type:
            if file_path.lower().endswith(".json"):
                format_type = "json"
            elif file_path.lower().endswith(".csv"):
                format_type = "csv"
            else:
                # Try to detect by content
                try:
                    json.loads(content)
                    format_type = "json"
                except json.JSONDecodeError:
                    format_type = "csv"

        if format_type == "json":
            data = self.parse_json(content)
        else:
            data = self.parse_csv(content)

        if options["dry_run"]:
            self.show_import_preview(data, options["update_existing"])
        else:
            self.import_data(data, options["update_existing"])

    def parse_json(self, content):
        """Parse JSON content."""
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON format: {e}")

    def parse_csv(self, content):
        """Parse CSV content."""
        try:
            reader = csv.DictReader(content.splitlines())
            return list(reader)
        except Exception as e:
            raise CommandError(f"Error parsing CSV: {e}")

    def show_import_preview(self, data, update_existing):
        """Show what would be imported."""
        self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
        self.stdout.write("")

        new_count = 0
        update_count = 0
        skip_count = 0

        for item in data:
            label = item.get("label")
            if not label:
                self.stdout.write(self.style.ERROR(f"Skipping item without label: {item}"))
                skip_count += 1
                continue

            try:
                TranslationString.objects.get(label=label)
                if update_existing:
                    self.stdout.write(f"Would UPDATE: {label}")
                    update_count += 1
                else:
                    self.stdout.write(f"Would SKIP: {label} (already exists)")
                    skip_count += 1
            except TranslationString.DoesNotExist:
                self.stdout.write(f"Would CREATE: {label}")
                new_count += 1

        self.stdout.write("")
        self.stdout.write(f"Summary: {new_count} new, {update_count} updates, {skip_count} skipped")

    @transaction.atomic
    def import_data(self, data, update_existing):
        """Import the actual data."""
        new_count = 0
        update_count = 0
        skip_count = 0
        error_count = 0

        for item in data:
            label = item.get("label")
            if not label:
                self.stdout.write(self.style.ERROR(f"Skipping item without label: {item}"))
                error_count += 1
                continue

            value = item.get("value", "")
            description = item.get("description", "")
            is_active = item.get("is_active", True)

            # Convert string booleans
            if isinstance(is_active, str):
                is_active = is_active.lower() in ("true", "1", "yes", "on")

            try:
                obj, created = TranslationString.objects.get_or_create(
                    label=label,
                    defaults={
                        "value": value,
                        "description": description,
                        "is_active": is_active,
                    },
                )

                if created:
                    self.stdout.write(f"Created: {label}")
                    new_count += 1
                elif update_existing:
                    obj.value = value
                    obj.description = description
                    obj.is_active = is_active

                    # Handle translation fields
                    translations = item.get("translations", {})
                    for lang_code, translated_value in translations.items():
                        field_name = f"value_{lang_code}"
                        if hasattr(obj, field_name):
                            setattr(obj, field_name, translated_value)

                    obj.save()
                    self.stdout.write(f"Updated: {label}")
                    update_count += 1
                else:
                    self.stdout.write(f"Skipped: {label} (already exists)")
                    skip_count += 1

                # Handle translation fields for new objects too
                if created:
                    translations = item.get("translations", {})
                    if translations:
                        for lang_code, translated_value in translations.items():
                            field_name = f"value_{lang_code}"
                            if hasattr(obj, field_name):
                                setattr(obj, field_name, translated_value)
                        obj.save()

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error importing {label}: {e}"))
                error_count += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Import completed: {new_count} created, {update_count} updated, {skip_count} skipped, {error_count} errors"))

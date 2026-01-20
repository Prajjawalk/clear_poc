"""Management command to export translations to JSON/CSV."""

import csv
import json
from io import StringIO

from django.conf import settings
from django.core.management.base import BaseCommand

from ...models import TranslationString


class Command(BaseCommand):
    """Export translations to JSON or CSV format."""

    help = "Export translation strings to JSON or CSV format"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--format",
            choices=["json", "csv"],
            default="json",
            help="Export format (default: json)",
        )
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            help="Output file path (default: stdout)",
        )
        parser.add_argument(
            "--active-only",
            action="store_true",
            help="Export only active translations",
        )


    def handle(self, *args, **options):
        """Handle the command execution."""
        queryset = TranslationString.objects.all()

        if options["active_only"]:
            queryset = queryset.filter(is_active=True)

        queryset = queryset.order_by("label")

        if options["format"] == "json":
            content = self.export_json(queryset)
        else:
            content = self.export_csv(queryset)

        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as f:
                f.write(content)
            self.stdout.write(self.style.SUCCESS(f"Successfully exported {queryset.count()} translations to {options['output']}"))
        else:
            self.stdout.write(content)

    def export_json(self, queryset):
        """Export translations to JSON format."""
        field_names = ["label", "description", "is_active", "created_at", "updated_at"]
        for lang_code, _lang_name in settings.LANGUAGES:
            field_names.append(f"value_{lang_code}")

        data = []
        for row in queryset.values(*field_names):
            # Convert datetime objects to ISO format strings
            if 'created_at' in row and row['created_at']:
                row['created_at'] = row['created_at'].isoformat()
            if 'updated_at' in row and row['updated_at']:
                row['updated_at'] = row['updated_at'].isoformat()
            data.append(row)

        return json.dumps(data, indent=2, ensure_ascii=False)

    def export_csv(self, queryset):
        """Export translations to CSV format."""
        output = StringIO()

        fieldnames = ["label", "description", "is_active", "created_at", "updated_at"]
        for lang_code, _lang_name in settings.LANGUAGES:
            fieldnames.append(f"value_{lang_code}")

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for row_data in queryset.values_list(*fieldnames):
            row = dict(zip(fieldnames, row_data, strict=False))
            # Convert datetime objects to ISO format strings for CSV
            if 'created_at' in row and row['created_at']:
                row['created_at'] = row['created_at'].isoformat()
            if 'updated_at' in row and row['updated_at']:
                row['updated_at'] = row['updated_at'].isoformat()
            writer.writerow(row)

        return output.getvalue()

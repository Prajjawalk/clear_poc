"""Management command to scan codebase for translation strings and add missing ones."""

import os
import re
from pathlib import Path

from django.core.management.base import BaseCommand

from ...models import TranslationString


class Command(BaseCommand):
    """Scan codebase for translation strings and add missing ones to database."""

    help = "Scan codebase for translation strings and add missing ones to the database"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--path",
            type=str,
            default=".",
            help="Path to scan for translation strings (default: current directory)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating it",
        )
        parser.add_argument(
            "--include-existing",
            action="store_true",
            help="Show existing translations in addition to missing ones",
        )
        parser.add_argument(
            "--file-extensions",
            type=str,
            default="py,html,txt",
            help="Comma-separated file extensions to scan (default: py,html,txt)",
        )
        parser.add_argument(
            "--exclude-dirs",
            type=str,
            default="migrations,__pycache__,.git,node_modules,venv,.venv,env,.env",
            help="Comma-separated directories to exclude from scan",
        )

    def handle(self, *args, **options):
        """Handle the command."""
        scan_path = Path(options["path"]).resolve()
        dry_run = options["dry_run"]
        include_existing = options["include_existing"]
        file_extensions = [ext.strip() for ext in options["file_extensions"].split(",")]
        exclude_dirs = [dir.strip() for dir in options["exclude_dirs"].split(",")]

        if not scan_path.exists():
            self.stderr.write(self.style.ERROR(f"Path does not exist: {scan_path}"))
            return

        self.stdout.write(f"Scanning for translation strings in: {scan_path}")
        self.stdout.write(f"File extensions: {', '.join(file_extensions)}")
        self.stdout.write(f"Excluded directories: {', '.join(exclude_dirs)}")
        self.stdout.write("")

        # Scan for translation strings
        found_labels = self.scan_for_translations(scan_path, file_extensions, exclude_dirs)

        if not found_labels:
            self.stdout.write(self.style.WARNING("No translation strings found in codebase."))
            return

        # Get existing translations
        existing_labels = set(TranslationString.objects.values_list("label", flat=True))

        # Separate existing and missing
        missing_labels = found_labels - existing_labels
        existing_found = found_labels & existing_labels

        # Report results
        self.stdout.write(f"Found {len(found_labels)} unique translation strings in codebase")

        if include_existing and existing_found:
            self.stdout.write(f"\n{self.style.SUCCESS('Existing translations:')}")
            for label in sorted(existing_found):
                self.stdout.write(f"  ✓ {label}")

        if missing_labels:
            self.stdout.write(f"\n{self.style.WARNING(f'Missing translations ({len(missing_labels)}):')}")
            for label in sorted(missing_labels):
                self.stdout.write(f"  - {label}")

            if dry_run:
                self.stdout.write(f"\n{self.style.NOTICE('DRY RUN: Would create the above missing translations.')}")
            else:
                self.stdout.write(f"\nCreating {len(missing_labels)} missing translations...")
                created_count = self.create_missing_translations(missing_labels)
                self.stdout.write(self.style.SUCCESS(f"Successfully created {created_count} translation strings."))
        else:
            self.stdout.write(f"\n{self.style.SUCCESS('All translation strings found in codebase already exist in database.')}")

    def scan_for_translations(self, scan_path, file_extensions, exclude_dirs):
        """
        Scan for translation strings in the codebase.

        Returns:
            Set of translation labels found
        """
        found_labels = set()

        # Patterns to match translation strings
        patterns = [
            # Template tags: {% translate "label" %}, {% trans "label" %}
            r'{%\s*(?:translate|trans)\s+["\']([^"\']+)["\']',
            # Template filters: {{ "label"|t }}
            r'{{\s*["\']([^"\']+)["\']\s*\|\s*t\s*}}',
            # Python function calls: translate("label"), translate('label')
            r'translate\s*\(\s*["\']([^"\']+)["\']',
            # Alternative quotes
            r'translate\s*\(\s*"([^"]+)"',
            r"translate\s*\(\s*'([^']+)'",
            # Direct template tag calls in Python
            r'translation_tags\.translate\s*\(\s*["\']([^"\']+)["\']',
        ]

        compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

        files_scanned = 0
        for file_path in self.get_files_to_scan(scan_path, file_extensions, exclude_dirs):
            files_scanned += 1
            try:
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                    for pattern in compiled_patterns:
                        matches = pattern.findall(content)
                        for match in matches:
                            # Clean the label (remove extra whitespace)
                            label = match.strip()
                            if label and not label.startswith("{"):  # Avoid template variables
                                found_labels.add(label)

            except Exception as e:
                self.stderr.write(f"Error reading {file_path}: {e}")

        # Debug output
        if files_scanned == 0:
            self.stderr.write("No files were scanned - check path and file extensions")

        return found_labels

    def get_files_to_scan(self, scan_path, file_extensions, exclude_dirs):
        """
        Get list of files to scan based on extensions and exclusions.

        Yields:
            Path objects for files to scan
        """
        # If scan_path is a file, just yield it if it matches extensions
        if scan_path.is_file():
            if scan_path.suffix.lstrip(".").lower() in [ext.lower() for ext in file_extensions]:
                yield scan_path
            return

        # If scan_path is a directory, walk through it
        for root, dirs, files in os.walk(scan_path):
            # Remove excluded directories from the search
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                file_path = Path(root) / file

                # Check if file has allowed extension
                if file_path.suffix.lstrip(".").lower() in [ext.lower() for ext in file_extensions]:
                    yield file_path

    def create_missing_translations(self, missing_labels):
        """
        Create missing translation strings in the database.

        Args:
            missing_labels: Set of labels to create

        Returns:
            Number of translations created
        """
        created_count = 0

        for label in missing_labels:
            try:
                TranslationString.objects.create(
                    label=label,
                    value=label,  # Use label as default value
                    description="Auto-discovered from codebase scan",
                    is_active=True,
                )
                created_count += 1

            except Exception as e:
                self.stderr.write(f'Error creating translation for "{label}": {e}')

        return created_count

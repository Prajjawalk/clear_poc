"""Management command to configure auto-creation of missing translation strings."""

from django.core.management.base import BaseCommand

from ...utils import get_auto_create_setting, set_auto_create_setting


class Command(BaseCommand):
    """Configure auto-creation of missing translation strings."""

    help = "Enable or disable automatic creation of missing translation strings"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--enable",
            action="store_true",
            help="Enable auto-creation of missing translation strings",
        )
        parser.add_argument(
            "--disable",
            action="store_true",
            help="Disable auto-creation of missing translation strings",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show current auto-creation status",
        )

    def handle(self, *args, **options):
        """Handle the command."""
        if options["enable"] and options["disable"]:
            self.stderr.write(self.style.ERROR("Cannot specify both --enable and --disable"))
            return

        if options["enable"]:
            set_auto_create_setting(True)
            self.stdout.write(self.style.SUCCESS("Auto-creation of missing translation strings: ENABLED"))
            self.stdout.write("Missing translation strings will now be automatically created in the database.")

        elif options["disable"]:
            set_auto_create_setting(False)
            self.stdout.write(self.style.SUCCESS("Auto-creation of missing translation strings: DISABLED"))
            self.stdout.write("Missing translation strings will return the label as fallback without database creation.")

        elif options["status"]:
            current_status = get_auto_create_setting()
            status_text = "ENABLED" if current_status else "DISABLED"
            color = self.style.SUCCESS if current_status else self.style.WARNING

            self.stdout.write(color(f"Auto-creation of missing translation strings: {status_text}"))

            if current_status:
                self.stdout.write("Missing translation strings will be automatically created in the database.")
            else:
                self.stdout.write("Missing translation strings will return the label as fallback without database creation.")
        else:
            # Show usage if no action specified
            current_status = get_auto_create_setting()
            status_text = "ENABLED" if current_status else "DISABLED"
            color = self.style.SUCCESS if current_status else self.style.WARNING

            self.stdout.write(color(f"Current status: Auto-creation is {status_text}"))
            self.stdout.write("")
            self.stdout.write("Usage:")
            self.stdout.write("  --enable    Enable auto-creation")
            self.stdout.write("  --disable   Disable auto-creation")
            self.stdout.write("  --status    Show current status")
            self.stdout.write("")
            self.stdout.write("Note: Changes are runtime only. For permanent changes, modify TRANSLATION_AUTO_CREATE_MISSING in settings.")

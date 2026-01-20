"""Management command to set up LLM providers from fixtures."""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction

from llm_service.models import ProviderConfig


class Command(BaseCommand):
    """Set up LLM providers from fixtures."""

    help = "Set up LLM provider configurations from fixtures"

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Clear existing providers before loading fixtures',
        )
        parser.add_argument(
            '--fixture',
            default='providers.json',
            help='Fixture file to load (default: providers.json)',
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        self.stdout.write("Setting up LLM providers...")

        with transaction.atomic():
            if options['reset']:
                self.stdout.write("Clearing existing provider configurations...")
                deleted_count = ProviderConfig.objects.count()
                ProviderConfig.objects.all().delete()
                self.stdout.write(
                    self.style.SUCCESS(f"Deleted {deleted_count} existing providers")
                )

            # Load fixtures
            fixture_path = f"llm_service/fixtures/{options['fixture']}"
            self.stdout.write(f"Loading fixture: {fixture_path}")

            try:
                call_command('loaddata', fixture_path, verbosity=0)

                # Count loaded providers
                provider_count = ProviderConfig.objects.count()

                self.stdout.write(
                    self.style.SUCCESS(f"Successfully loaded {provider_count} providers")
                )

                # Display loaded providers
                self.stdout.write("\nLoaded providers:")
                for provider in ProviderConfig.objects.order_by('-priority'):
                    status = "✓ Active" if provider.is_active else "✗ Inactive"
                    model = provider.config.get('MODEL', 'Unknown')
                    self.stdout.write(
                        f"  {provider.provider_name} ({model}) - Priority: {provider.priority} - {status}"
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to load fixtures: {str(e)}")
                )
                raise

        self.stdout.write(
            self.style.SUCCESS("\nLLM providers setup completed!")
        )
        self.stdout.write(
            "Next steps:\n"
            "1. Ensure LITELLM_API_KEY is set in your .env file\n"
            "2. Configure your LiteLLM proxy to support these models\n"
            "3. Test providers with: uv run manage.py test_llm_provider <provider_name>"
        )
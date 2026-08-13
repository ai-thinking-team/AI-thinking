from django.core.management.base import BaseCommand, CommandError

from apps.ai_engine.health import probe_ai_provider


class Command(BaseCommand):
    help = 'Call the configured AI provider with a data-free structured health check.'

    def handle(self, *args, **options):
        result = probe_ai_provider()
        detail = f"{result['code']} ({result['latency_ms']} ms): {result['message']}"
        if not result['available']:
            raise CommandError(detail)
        self.stdout.write(self.style.SUCCESS(detail))

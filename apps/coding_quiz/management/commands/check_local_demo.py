import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand, CommandError

from apps.coding_quiz.catalog import CODING_CATALOG
from apps.coding_quiz.catalog_validation import validate_catalog


class Command(BaseCommand):
    help = 'Check local Django/Coding catalog and isolated runner readiness.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-runner',
            action='store_true',
            help='Check Django and catalog only; do not contact the runner.',
        )

    def handle(self, *args, **options):
        management.call_command('check', verbosity=0)
        errors = validate_catalog(CODING_CATALOG)
        if errors:
            raise CommandError('Catalog validation failed:\n- ' + '\n- '.join(errors))
        self.stdout.write(self.style.SUCCESS('Django checks: OK'))
        self.stdout.write(self.style.SUCCESS(f'Coding catalog: OK ({len(CODING_CATALOG)} exercises)'))

        if options['skip_runner']:
            self.stdout.write('Runner check: skipped')
            return

        runner_url = getattr(settings, 'CODE_RUNNER_URL', '').strip()
        if not runner_url:
            raise CommandError('CODE_RUNNER_URL is empty; start local runner or use --skip-runner.')
        health_url = runner_url.rstrip('/')
        if health_url.endswith('/execute'):
            health_url = health_url[:-len('/execute')]
        health_url += '/health'
        try:
            with urlopen(health_url, timeout=3) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise CommandError(f'Runner health check failed at {health_url}: {exc}') from exc
        if payload.get('status') != 'ok':
            raise CommandError(f'Runner health check returned an unexpected response: {payload}')
        self.stdout.write(self.style.SUCCESS(f'Runner health: OK ({health_url})'))

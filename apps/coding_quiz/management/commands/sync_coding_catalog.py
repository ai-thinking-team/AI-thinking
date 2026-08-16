from django.core.management.base import BaseCommand, CommandError

from apps.coding_quiz.catalog import CODING_CATALOG
from apps.coding_quiz.catalog_sync import sync_catalog


class Command(BaseCommand):
    help = 'Validate and upsert the Coding catalog without deleting existing exercises or history.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Validate and report changes without writing.')

    def handle(self, *args, **options):
        try:
            report = sync_catalog(catalog=CODING_CATALOG, dry_run=options['dry_run'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        mode = 'Dry run' if options['dry_run'] else 'Synced'
        self.stdout.write(f'{mode}: created={len(report["created"])} updated={len(report["updated"])} unchanged={len(report["unchanged"])}')
        for key in ('created', 'updated', 'unchanged'):
            if report[key]:
                self.stdout.write(f'{key}: {", ".join(report[key])}')

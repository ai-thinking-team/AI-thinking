from django.core.management.base import BaseCommand, CommandError

from apps.coding_quiz.catalog import CODING_CATALOG
from apps.coding_quiz.catalog_validation import validate_catalog


class Command(BaseCommand):
    help = 'Validate the version-controlled Coding exercise catalog and runner test IDs.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        errors = validate_catalog(CODING_CATALOG)
        if options['as_json']:
            import json
            self.stdout.write(json.dumps({'valid': not errors, 'errors': errors}, ensure_ascii=False))
        if errors:
            raise CommandError('Catalog validation failed:\n- ' + '\n- '.join(errors))
        self.stdout.write(self.style.SUCCESS(f'Catalog valid: {len(CODING_CATALOG)} exercise(s).'))

from django.core.management.base import BaseCommand, CommandError
from computedfields.models import active_resolver
from django.conf import settings


class Command(BaseCommand):
    help = 'Pickle dependency lookup map for computed fields to file.'

    def handle(self, *args, **options):
        if not hasattr(settings, 'COMPUTEDFIELDS_MAP'):
            raise CommandError('COMPUTEDFIELDS_MAP is not set in settings.py, abort.')

        active_resolver._write_pickled_data()

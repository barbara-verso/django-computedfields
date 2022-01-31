from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.db import transaction
from computedfields.models import active_resolver
from computedfields.helper import modelname, slice_iterator
from computedfields.settings import settings
from time import time
from datetime import timedelta


class _Tqdm:
    def __init__(self, *args, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        pass
    def update(self, *args):
        pass


try:
    from tqdm import tqdm
except ImportError:
    tqdm = _Tqdm


class Command(BaseCommand):
    help = 'Update computed fields.'

    def add_arguments(self, parser):
        parser.add_argument(
            'args', metavar='app_label[.ModelName]', nargs='*',
            help='Update computed fields in specified app_label or app_label.ModelName.',
        )
        parser.add_argument(
            '-p', '--progress',
            action='store_true',
            help='show update progress',
        )
        parser.add_argument(
            '-m', '--mode',
            default='default',
            type=str,
            choices=('loop', 'bulk', 'fast'),
            help='update mode, default: bulk/fast from settings.py'
        )
        parser.add_argument(
            '-q', '--querysize',
            default=settings.COMPUTEDFIELDS_QUERYSIZE,
            type=int,
            help='queryset size, default: 2000 or value from settings.py'
        )

    def handle(self, *app_labels, **options):
        # FIXME: remove once tests are fixed
        #for model in active_resolver.computed_models:
        #    for obj in model.objects.all():
        #        obj.save()
        #return
        start_time = time()
        progress = options['progress']
        mode = options['mode']
        size = options['querysize']
        if progress and tqdm == _Tqdm:
            raise CommandError("Package 'tqdm' needed for the progressbar.")
        models = retrieve_computed_models(app_labels)
        getattr(self, 'action_' + mode, self.action_default)(models, size, progress)
        end_time = time()
        duration = int(end_time - start_time)
        print(f'\nTotal time: {timedelta(seconds=duration)}')

    @transaction.atomic
    def action_default(self, models, size, show_progress, mode=''):
        """
        Runs either in fast or bulk mode, whatever was set in settings.
        """
        # TODO: move this outside of transaction?
        if not mode:
            if settings.COMPUTEDFIELDS_FASTUPDATE:
                from computedfields.fast_update import check_support
                if check_support():
                    mode = 'fast'
            print(f'Update mode: settings.py --> {mode or "bulk"}')

        print(f'Global querysize: {size}')
        print('Models:')
        for model in models:
            qs = model.objects.all()
            amount = qs.count()
            fields = set(active_resolver.computed_models[model].keys())
            print(f'- {self.style.MIGRATE_LABEL(modelname(model))}')
            print(f'  Fields: {", ".join(fields)}')
            print(f'  Records: {amount}')
            print(f'  Querysize: {active_resolver.get_querysize(model, fields, size)}')
            if not amount:
                continue
            # FIXME: use slice interface from bulk_updater, once we have it
            pos = 0
            with tqdm(total=amount, desc='  Progress', unit=' rec', disable=not show_progress) as bar:
                active_resolver.update_dependent(qs, querysize=size)

                #while pos < amount:
                #    active_resolver.update_dependent(
                #        qs.order_by('pk')[pos:pos+size], querysize=size)
                #    progress = min(pos+size, amount) - pos
                #    bar.update(progress)
                #    pos += size

    def action_bulk(self, models, size, show_progress):
        active_resolver.use_fastupdate = False
        print('Update mode: bulk')
        self.action_default(models, size, show_progress, 'bulk')

    def action_fast(self, models, size, show_progress):
        from computedfields.fast_update import check_support
        if not check_support():
            raise CommandError('Current db backend does not support fast_update.')
        active_resolver.use_fastupdate = True
        active_resolver._batchsize = settings.COMPUTEDFIELDS_BATCHSIZE_FAST
        print('Update mode: fast')
        self.action_default(models, size, show_progress, 'fast')

    @transaction.atomic
    def action_loop(self, models, size, show_progress):
        # TODO: load select/prefetch from cfs?
        print('Update mode: loop')
        print(f'Global querysize: {size}')
        print('Models:')
        if size != settings.COMPUTEDFIELDS_QUERYSIZE:
            # patch django settings in case querysize was explicitly given
            # needed here, as we have no other API to announce the changed value
            from django.conf import settings as ds
            ds.COMPUTEDFIELDS_QUERYSIZE = size
        for model in models:
            qs = model.objects.all()
            amount = qs.count()
            fields = list(active_resolver.computed_models[model].keys())
            qsize = active_resolver.get_querysize(model, fields, size)
            print(f'- {self.style.MIGRATE_LABEL(modelname(model))}')
            print(f'  Fields: {", ".join(fields)}')
            print(f'  Records: {amount}')
            print(f'  Querysize: {qsize}')
            if not amount:
                continue
            # also apply select/prefetch rules
            select = active_resolver.get_select_related(model, fields)
            prefetch = active_resolver.get_prefetch_related(model, fields)
            if select:
                qs = qs.select_related(*select)
            if prefetch:
                qs = qs.prefetch_related(*prefetch)
            with tqdm(total=amount, desc='  Progress', unit=' rec', disable=not show_progress) as bar:
                for obj in slice_iterator(qs, qsize):
                    obj.save()
                    bar.update(1)


def retrieve_computed_models(app_labels):
    computed_models = set(active_resolver.computed_models.keys())
    if not app_labels:
        return computed_models
    update_models = set()
    for label in app_labels:
        app_model = label.split('.')
        try:
            app_config = apps.get_app_config(app_model[0])
        except LookupError as e:
            raise CommandError(str(e))
        if len(app_model) == 1:
            update_models |= set(app_config.get_models()) & computed_models
        elif len(app_model) == 2:
            try:
                update_models |= set([app_config.get_model(app_model[1])]) & computed_models
            except LookupError:
                raise CommandError(f'Unknown model: {label}')
        else:
            raise CommandError(f'Unsupported app_label.ModelName specification: {label}')
    return update_models

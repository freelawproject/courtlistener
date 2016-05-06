'''
    Hopefully this makes slicing out production data simpler.
'''
from django.core import serializers
from django.core.management.base import BaseCommand
from cl.search.models import Docket, OpinionCluster, Opinion


class Command(BaseCommand):
    help = ('Wraps the core dumpdata management command with CL friendly export'
            'settings')

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            '-n',
            type=int,
            default=10,
            help='Number of items in the export'
        )
        parser.add_argument(
            '--format',
            type=str,
            default='json',
            help='Serialization format [json, xml, yaml]'
        )
        parser.add_argument(
            '-o',
            type=str,
            default='dump.json',
            help='Name of output file to serialize data into'
        )

    def handle(self, *args, **options):
        n = options['n']
        fmt = options['format']

        self.stdout.write('-n was set to: %s' % n)

        pks = Opinion.objects.values_list('id', flat=True).order_by('?')[:n]
        opinions = Opinion.objects.filter(id__in=pks).all()
        self.stdout.write('Opinions:\n%s' % (opinions))

        clusters = OpinionCluster.objects.filter(sub_opinions__in=pks).all()
        self.stdout.write('Clusters:\n%s' % (clusters))

        dockets = Docket.objects.filter(clusters__in=clusters).all()
        self.stdout.write('Dockets:\n%s' % (dockets))

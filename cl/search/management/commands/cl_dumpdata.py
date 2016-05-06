'''
    Hopefully this makes slicing out production data simpler.
'''
from django.core import serializers
from django.core.management.base import BaseCommand
from cl.search.models import Docket, OpinionCluster, Opinion


class Command(BaseCommand):
    help = ('CL-specific data dumper for making fixtures from production')

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

    def handle(self, *args, **options):
        n = options['n']
        fmt = options['format']

        self.stdout.write(
            'Generating dump of up to %s randomly selected Opinions' % n
        )

        pks = Opinion.objects.values_list('id', flat=True).order_by('?')[:n]
        cluster_pks = OpinionCluster.objects.filter(sub_opinions__in=pks) \
                                    .values_list('id', flat=True).all()

        self.stdout.write('Writing Opinions to opinions.json...')
        with open('opinions.json', 'w') as stream:
            serializers.serialize(
                fmt,
                Opinion.objects.filter(id__in=pks).all(),
                stream=stream
            )

        self.stdout.write('Writing OpinionClusters to clusters.json...')
        with open('clusters.json', 'w') as stream:
            serializers.serialize(
                fmt,
                OpinionCluster.objects.filter(id__in=cluster_pks).all(),
                stream=stream
            )

        self.stdout.write('Writing Dockets to dockets.json...')
        with open('dockets.json', 'w') as stream:
            serializers.serialize(
                fmt,
                Docket.objects.filter(clusters__in=cluster_pks).all(),
                stream=stream
            )

        self.stdout.write('Done!')

import json

from django.core.management import BaseCommand

from cl.search.models import OpinionCluster
from cl.visualizations.models import JSONVersion


class Command(BaseCommand):
    help = "Upgrade JSON data from old format to new."

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.options = None
        self.json_objects = None
        self.num_objects = None

    def add_arguments(self, parser):
        parser.add_argument(
            '--start',
            type=float,
            help="The version we're upgrading from."
        )
        parser.add_argument(
            '--end',
            type=float,
            help="The version we're upgrading to"
        )

    def handle(self, *args, **options):
        self.options = options
        self.json_objects = JSONVersion.objects.all()
        self.num_objects = self.json_objects.count()
        print "Acting on %s objects" % self.num_objects
        self.upgrade_json(
            start=options['start'],
            end=options['end'],
            json_objects=self.json_objects,
        )

    @staticmethod
    def _upgrade_version_number(j, new_version):
        """Upgrade only the version number."""
        j['meta']['version'] = new_version
        return j

    def upgrade_json(self, start, end, json_objects):
        """Upgrade the objects if possible.

        Throw an exception of the version types mismatch.
        """
        for obj in json_objects:
            print "  Reworking %s" % obj
            if start == 1.0 and end == 1.1:
                j = json.loads(obj.json_data)
                j = self._upgrade_version_number(j, end)
                opinion_clusters = []
                for cluster in j['opinion_clusters']:
                    # Look up the ID, get the scdb_id value, and add it to the
                    # dict.
                    cluster_obj = OpinionCluster.objects.get(pk=cluster['id'])
                    cluster['scdb_id'] = getattr(cluster_obj, 'scdb_id', None)
                    opinion_clusters.append(cluster)
                j['opinion_clusters'] = opinion_clusters
                obj.json_data = json.dumps(j, indent=2)
                obj.save()

            else:
                raise NotImplementedError("Cannot upgrade from %s to %s" % (
                    start, end,
                ))

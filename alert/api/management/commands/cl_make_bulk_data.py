import StringIO
import os
import shutil
import tarfile
import time
import errno

from alert.lib.db_tools import queryset_generator
from alert.lib.timer import print_timing
from alert.search.models import Court, Document
from django.core.management import BaseCommand
from django.conf import settings
from audio.models import Audio


def mkdir_p(path):
    """Makes a directory path, but doesn't crash if the path already exists."""
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


class Command(BaseCommand):
    help = 'Create the bulk files for all jurisdictions and for "all".'

    def handle(self, *args, **options):
        self.do_everything()

    @print_timing
    def do_everything(self):
        """We can't wrap the handle() function, but we can wrap this one."""
        from alert.search import api2
        self.stdout.write('Starting bulk file creation...\n')
        arg_tuples = (
            ('opinion', Document, api2.DocumentResource),
            ('oral-argument', Audio, api2.OralArgumentResource),
        )
        for obj_type_str, obj_type, api_resource_obj in arg_tuples:
            self.make_archive(obj_type_str, obj_type, api_resource_obj)
            self.swap_archives(obj_type_str)
        self.stdout.write('Done.\n\n')

    def swap_archives(self, obj_type_str):
        """Swap out new archives for the old."""
        self.stdout.write(' - Swapping in the new %s archives...\n'
                          % obj_type_str)
        mkdir_p(os.path.join(settings.DUMP_DIR, '%s' % obj_type_str))
        for f in os.listdir('/tmp/bulk/%s' % obj_type_str):
            shutil.move('/tmp/bulk/%s/%s' % (obj_type_str, f),
                        os.path.join(settings.DUMP_DIR, '%ss' % obj_type_str))

    def make_archive(self, obj_type_str, obj_type, api_resource_obj):
        """Generate compressed archives containing the contents of an object
        database.

        There are a few tricks to this, but the main one is that each item in
        the database goes into two files, all.tar.gz and {court}.tar.gz. This
        means that if we want to avoid iterating the database once per file,
        we need to generate all 350+ jurisdiction files simultaneously.

        We do this by making a dict of open file handles and adding each item
        to the correct two files: The all.tar.gz file and the {court}.tar.gz
        file.
        """
        courts = Court.objects.all()
        self.stdout.write(' - Creating %s bulk %s files '
                          'simultaneously...\n' % (len(courts), obj_type_str))

        mkdir_p('/tmp/bulk/%s' % obj_type_str)

        # Open a gzip'ed tar file for every court
        tar_files = {}
        for court in courts:
            tar_files[court.pk] = tarfile.open(
                '/tmp/bulk/%s/%s.tar.gz' % (obj_type_str, court.pk),
                mode='w:gz'
            )
        tar_files['all'] = tarfile.open(
            '/tmp/bulk/%s/all.tar.gz' % obj_type_str,
            mode='w:gz'
        )

        # Make the archives
        qs = obj_type.objects.all()
        item_resource = api_resource_obj()
        item_list = queryset_generator(qs)
        for item in item_list:
            json_str = item_resource.serialize(
                None,
                item_resource.full_dehydrate(
                    item_resource.build_bundle(obj=item)),
                'application/json',
            ).encode('utf-8')

            # Add the json str to the two tarballs
            tarinfo = tarfile.TarInfo("%s.json" % item.pk)
            tarinfo.size = len(json_str)
            tarinfo.mtime = time.mktime(item.date_modified.timetuple())
            tarinfo.type = tarfile.REGTYPE

            tar_files[item.docket.court_id].addfile(
                tarinfo, StringIO.StringIO(json_str))
            tar_files['all'].addfile(
                tarinfo, StringIO.StringIO(json_str))

        # Close off all the gzip'ed tar files
        for court in courts:
            tar_files[court.pk].close()
        tar_files['all'].close()

        self.stdout.write(' - all %s bulk files created.\n' % obj_type_str)

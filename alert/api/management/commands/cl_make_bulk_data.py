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
    except OSError as exc:
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
                        os.path.join(settings.DUMP_DIR, '%s' % obj_type_str, f))

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

        This function takes longer to run than almost any in the codebase and
        has been the subject of some profiling. The top results are as follows:

           ncalls  tottime  percall  cumtime  percall filename:lineno(function)
           138072    5.007    0.000    6.138    0.000 {method 'sub' of '_sre.SRE_Pattern' objects}
             6001    4.452    0.001    4.608    0.001 {method 'execute' of 'psycopg2._psycopg.cursor' objects}
            24900    3.623    0.000    3.623    0.000 {built-in method compress}
        2807031/69163    2.923    0.000    8.216    0.000 copy.py:145(deepcopy)
          2427852    0.952    0.000    1.130    0.000 encoder.py:37(replace)

        Conclusions:
         1. sub is from string_utils.py, where we nuke bad chars. Could remove
            this code by sanitizing all future input to system and fixing any
            current issues. Other than that, it's already optimized.
         1. Next up is DB waiting. Queries could be optimized to make this
            better.
         1. Next is compression, which we've turned down as much as possible
            already (compresslevel=1 for most bulk files =3 for all.tar.gz).
         1. Encoding and copying bring up the rear. Not much to do there, and
            gains are limited. Could install a faster json decoder, but Python
            2.7's json implementation is already written in C. Not sure how to
            remove the gazillion copy's that are happening.
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
                mode='w:gz',
                compresslevel=1,
            )
        tar_files['all'] = tarfile.open(
            '/tmp/bulk/%s/all.tar.gz' % obj_type_str,
            mode='w:gz',
            compresslevel=3,
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

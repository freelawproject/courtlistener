import errno
import StringIO
import glob
import gzip
import os

import shutil
import tarfile
import time
import datetime

from django.core.management import BaseCommand
from django.conf import settings
from django.utils.timezone import now

from alert.audio.models import Audio
from alert.lib.db_tools import queryset_generator
from alert.lib.timer import print_timing
from alert.search.models import Court, Document, Docket


def deepgetattr(obj, attr):
    """Recurse through an attribute chain to get the ultimate value."""
    return reduce(getattr, attr.split('.'), obj)


def swap_archives(obj_type_str):
    """Swap out new archives, clobbering the old, if present"""
    mkdir_p(os.path.join(settings.BULK_DATA_DIR, '%s' % obj_type_str))
    path_to_gz_files = os.path.join(settings.BULK_DATA_DIR, 'tmp',
                                    obj_type_str, '*.tar*')
    for f in glob.glob(path_to_gz_files):
        shutil.move(
            f,
            os.path.join(
                settings.BULK_DATA_DIR,
                obj_type_str,
                os.path.basename(f)
            )
        )


def compress_all_archives(obj_type_str):
    """Compresses all the archives in place. Once ready, they are moved to
    the correct location.
    """
    path_to_tars = os.path.join(
        settings.BULK_DATA_DIR, 'tmp', obj_type_str, '*.tar')
    for tar_path in glob.glob(path_to_tars):
        tar_file_in = open(tar_path, 'rb')
        gz_out = gzip.open('%s.gz' % tar_path, 'wb')
        gz_out.writelines(tar_file_in)
        gz_out.close()
        tar_file_in.close()


def tar_and_compress_all_json_files(obj_type_str, courts):
    """Create gz-compressed archives using the JSON on disk."""
    for court in courts:
        tar = tarfile.open(
            os.path.join(
                settings.BULK_DATA_DIR,
                'tmp',
                obj_type_str,
                '%s.tar.gz' % court.pk),
            "w:gz", compresslevel=6)
        for name in glob.glob(os.path.join(
                settings.BULK_DATA_DIR,
                'tmp',
                obj_type_str,
                court.pk,
                "*.json")):
            tar.add(name, arcname=os.path.basename(name))
        tar.close()

    # Make the all.tar.gz file by tarring up the other files.
    tar = tarfile.open(
        os.path.join(
            settings.BULK_DATA_DIR,
            'tmp',
            obj_type_str,
            'all.tar'),
        "w")
    for court in courts:
        targz = os.path.join(
            settings.BULK_DATA_DIR,
            'tmp',
            obj_type_str,
            "%s.tar.gz" % court.pk)
        tar.add(targz, arcname=os.path.basename(targz))
    tar.close()


def mkdir_p(path):
    """Makes a directory path, but doesn't crash if the path already exists."""
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def test_if_old_bulk_files_exist(obj_type_str):
    """We assume that if there are directories here, then the system has run
    previously.
    """
    path_to_bulk_files = os.path.join(settings.BULK_DATA_DIR, 'tmp',
                                      obj_type_str, '*')
    if glob.glob(path_to_bulk_files):
        # Some stuff was in there!
        return True
    else:
        return False


class Command(BaseCommand):
    help = 'Create the bulk files for all jurisdictions and for "all".'

    def handle(self, *args, **options):
        self.do_everything()

    @print_timing
    def do_everything(self):
        """We can't wrap the handle() function, but we can wrap this one."""
        from alert.search import api2
        self.stdout.write('Starting bulk file creation...\n')

        # Make the main bulk files
        arg_tuples = (
            ('document', Document, 'docket.court_id', api2.DocumentResource),
            ('audio', Audio, 'docket.court_id', api2.AudioResource),
            ('docket', Docket, 'court_id', api2.DocketResource),
            ('jurisdiction', Court, 'pk', api2.JurisdictionResource),
        )
        courts = Court.objects.all()
        for obj_type_str, obj_type, court_attr, api_resource_obj in arg_tuples:
            self.stdout.write(
                ' - Creating %s bulk %s files...\n' %
                (len(courts), obj_type_str))
            self.write_json_to_disk(obj_type_str, obj_type, court_attr,
                                    api_resource_obj, courts)

            self.stdout.write(
                '   - Tarring and compressing all %s files...\n' %
                obj_type_str)
            tar_and_compress_all_json_files(obj_type_str, courts)

            self.stdout.write(
                '   - Swapping in the new %s archives...\n'
                % obj_type_str)
            swap_archives(obj_type_str)

        # Make the citation bulk data
        self.make_citation_data()
        self.stdout.write("   - Swapping in the new citation archives...\n")
        swap_archives('citation')

        self.stdout.write('Done.\n\n')

    def write_json_to_disk(self, obj_type_str, obj_type, court_attr,
                           api_resource_obj, courts):
        """Write all items to disk as json files inside directories named by
        jurisdiction.

        The main trick is that we identify if we are creating a bulk archive
        from scratch. If so, we iterate over everything. If not, we only
        iterate over items that have been modified in the last 32 days because
        it's assumed that the bulk files are generated once per month.
        """
        # Are there already bulk files?
        incremental = test_if_old_bulk_files_exist(obj_type_str)

        # Create a directory for every jurisdiction, if they don't already
        # exist. This does not clobber.
        for court in courts:
            mkdir_p(os.path.join(
                settings.BULK_DATA_DIR,
                'tmp',
                obj_type_str,
                court.pk,
            ))

        if incremental:
            # Make the archives with updates from the last 32 days.
            self.stdout.write(
                "   - Using incremental mode...\n")
            thirty_two_days_ago = now() - datetime.timedelta(days=32)
            qs = obj_type.objects.filter(date_modified__gt=thirty_two_days_ago)
        else:
            qs = obj_type.objects.all()
        item_resource = api_resource_obj()
        if type(qs[0].pk) == int:
            item_list = queryset_generator(qs)
        else:
            item_list = qs
        i = 0
        for item in item_list:
            json_str = item_resource.serialize(
                None,
                item_resource.full_dehydrate(
                    item_resource.build_bundle(obj=item)),
                'application/json',
            ).encode('utf-8')

            with open(os.path.join(
                settings.BULK_DATA_DIR,
                'tmp',
                obj_type_str,
                deepgetattr(item, court_attr),
                '%s.json' % item.pk), 'wb') as f:
                f.write(json_str)
            i += 1

        self.stdout.write('   - all %s %s json files created.\n' %
                          (i, obj_type_str))

    def make_citation_data(self):
        """Because citations are paginated and because as of this moment there
        are 11M citations in the database, we cannot provide users with a bulk
        data file containing the complete objects for every citation.

        Instead of doing that, we dump our citation table with a shell command,
        which provides people with compact and reasonable data they can import.
        """
        mkdir_p('/tmp/bulk/citation')
        self.stdout.write(" - Creating bulk data CSV for citations...\n")
        self.stdout.write(
            '   - Copying the Document_cases_cited table to disk...\n')

        # This command calls the psql COPY command and requests that it dump
        # the document_id and citation_id columns from the Document_cases_cited
        # table to disk as a compressed CSV.
        os.system(
            '''psql -c "COPY \\"Document_cases_cited\\" (document_id, citation_id) to stdout DELIMITER ',' CSV HEADER" -d courtlistener --username django | gzip > /tmp/bulk/citation/all.csv.gz'''
        )
        self.stdout.write('   - Table created successfully.\n')

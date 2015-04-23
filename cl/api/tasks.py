import datetime
import glob
import os
import shutil
import tarfile

from celery.task import task
from django.conf import settings
from django.utils.timezone import now

from cl.lib.timer import print_timing
from cl.lib.db_tools import queryset_generator
from cl.lib.utils import deepgetattr
from cl.lib.utils import mkdir_p


@task
@print_timing
def make_bulk_data_and_swap_it_in(arg_tuple, courts):
    """We can't wrap the handle() function, but we can wrap this one."""
    obj_type_str, obj_type, court_attr, api_resource_obj = arg_tuple

    print ' - Creating %s bulk %s files...' % (len(courts), obj_type_str)
    write_json_to_disk(obj_type_str, obj_type, court_attr, api_resource_obj,
                       courts)

    print '   - Tarring and compressing all %s files...' % obj_type_str
    tar_and_compress_all_json_files(obj_type_str, courts)

    print '   - Swapping in the new %s archives...' % obj_type_str
    swap_archives(obj_type_str)


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


def tar_and_compress_all_json_files(obj_type_str, courts):
    """Create gz-compressed archives using the JSON on disk."""
    for court in courts:
        tar = tarfile.open(
            os.path.join(
                settings.BULK_DATA_DIR,
                'tmp',
                obj_type_str,
                '%s.tar.gz' % court.pk),
            "w:gz", compresslevel=3)
        for name in glob.glob(os.path.join(
                settings.BULK_DATA_DIR,
                'tmp',
                obj_type_str,
                court.pk,
                "*.json")):
            tar.add(name, arcname=os.path.basename(name))
        tar.close()

    # Make the all.tar file by tarring up the other files.
    tar = tarfile.open(
        os.path.join(settings.BULK_DATA_DIR, 'tmp', obj_type_str, 'all.tar'),
        "w"
    )
    for court in courts:
        targz = os.path.join(
            settings.BULK_DATA_DIR,
            'tmp',
            obj_type_str,
            "%s.tar.gz" % court.pk)
        tar.add(targz, arcname=os.path.basename(targz))
    tar.close()


def write_json_to_disk(obj_type_str, obj_type, court_attr,
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
        # Make the archives using updated data from the last 32 days.
        print "   - Incremental data! We assume it's good, and use it..."
        thirty_two_days_ago = now() - datetime.timedelta(days=32)
        qs = obj_type.objects.filter(date_modified__gt=thirty_two_days_ago)
    else:
        print "   - Incremental data not found. Working from scratch..."
        qs = obj_type.objects.all()
    item_resource = api_resource_obj()
    if type(qs[0].pk) == int:
        item_list = queryset_generator(qs)
    else:
        # Necessary for jurisdictions, which don't have ints for ids.
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

    print '   - all %s %s json files created.' % (i, obj_type_str)


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

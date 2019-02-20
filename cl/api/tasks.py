import glob
import os
import shutil
import tarfile
from os.path import join

from django.conf import settings
from django.test import RequestFactory
from rest_framework.renderers import JSONRenderer
from rest_framework.versioning import URLPathVersioning

from cl.api.utils import BulkJsonHistory
from cl.celery import app
from cl.lib.db_tools import queryset_generator
from cl.lib.timer import print_timing
from cl.lib.utils import deepgetattr, mkdir_p


@app.task
@print_timing
def make_bulk_data_and_swap_it_in(courts, bulk_dir, kwargs):
    """We can't wrap the handle() function, but we can wrap this one."""
    # Create a directory where we'll put temporary files
    tmp_bulk_dir = join(bulk_dir, 'tmp')

    print(' - Creating bulk %s files...' % kwargs['obj_type_str'])
    num_written = write_json_to_disk(courts, bulk_dir=tmp_bulk_dir, **kwargs)

    if num_written > 0:
        print('   - Tarring and compressing all %s files...' %
              kwargs['obj_type_str'])
        targz_json_files(courts, tmp_bulk_dir, kwargs['obj_type_str'],
                         kwargs['court_attr'])

        print('   - Swapping in the new %s archives...' %
              kwargs['obj_type_str'])
        swap_archives(kwargs['obj_type_str'], bulk_dir, tmp_bulk_dir)


def swap_archives(obj_type_str, bulk_dir, tmp_bulk_dir):
    """Swap out new archives, clobbering the old, if present"""
    tmp_gz_dir = join(tmp_bulk_dir, obj_type_str)
    final_gz_dir = join(bulk_dir, obj_type_str)
    mkdir_p(final_gz_dir)
    for f in glob.glob(join(tmp_gz_dir, '*.tar*')):
        shutil.move(f, join(final_gz_dir, os.path.basename(f)))

    # Move the info files too.
    try:
        shutil.copy2(join(tmp_gz_dir, 'info.json'),
                     join(final_gz_dir, 'info.json'))
    except IOError as e:
        if e.errno == 2:
            # No such file/directory
            pass
        else:
            raise


def targz_json_files(courts, bulk_dir, obj_type_str, court_attr):
    """Create gz-compressed archives using the JSON on disk."""

    root_path = join(bulk_dir, obj_type_str)
    if court_attr is not None:
        for court in courts:
            tar_path = join(root_path, '%s.tar.gz' % court.pk)
            tar = tarfile.open(tar_path, "w:gz", compresslevel=3)
            for name in glob.glob(join(root_path, court.pk, "*.json")):
                tar.add(name, arcname=os.path.basename(name))
            tar.close()
    else:
        # Non-jurisdictional-centric object type (like an ABA Rating)
        tar_path = join(root_path, 'all.tar.gz')
        tar = tarfile.open(tar_path, 'w:gz', compresslevel=3)
        for name in glob.glob(join(root_path, '*.json')):
            tar.add(name, arcname=os.path.basename(name))
        tar.close()

    if court_attr is not None:
        # Make the all.tar file by tarring up the other files. Non-court-centric
        # objects already did this.
        tar = tarfile.open(join(root_path, 'all.tar'), "w")
        for court in courts:
            targz = join(root_path, "%s.tar.gz" % court.pk)
            tar.add(targz, arcname=os.path.basename(targz))
        tar.close()


def write_json_to_disk(courts, obj_type_str, obj_class, court_attr,
                       serializer, bulk_dir):
    """Write all items to disk as json files inside directories named by
    jurisdiction.

    The main trick is that we identify if we are creating a bulk archive
    from scratch. If so, we iterate over everything. If not, we only
    iterate over items that have been modified since the last good date.

    We deal with two kinds of bulk data. The first is jurisdiction-centric, in
    which we want to make bulk data for that particular jurisdiction, such as
    opinions or PACER data, or whatever. The second is non-jurisdiction-
    specific, like people or schools. For jurisdiction-specific data, we make
    jurisdiction directories to put the data into. Otherwise, we do not.

    :param courts: Court objects that you expect to make data for.
    :param obj_type_str: A string to use for the directory name of a type of
    data. For example, for clusters, it's 'clusters'.
    :param obj_class: The actual class to make a bulk data for.
    :param court_attr: A string that can be used to find the court attribute
    on an object. For example, on clusters, this is currently docket.court_id.
    :param serializer: A DRF serializer to use to generate the data.
    :param bulk_dir: A directory to place the serialized JSON data into.

    :returns int: The number of items generated
    """
    # Are there already bulk files?
    history = BulkJsonHistory(obj_type_str, bulk_dir)
    last_good_date = history.get_last_good_date()
    history.add_current_attempt_and_save()

    if court_attr is not None:
        # Create a directory for every jurisdiction, if they don't already
        # exist. This does not clobber.
        for court in courts:
            mkdir_p(join(
                bulk_dir,
                obj_type_str,
                court.pk,
            ))
    else:
        # Make a directory for the object type.
        mkdir_p(join(bulk_dir, obj_type_str))

    if last_good_date is not None:
        print("   - Incremental data found. Assuming it's good and using it...")
        qs = obj_class.objects.filter(date_modified__gte=last_good_date)
    else:
        print("   - Incremental data not found. Working from scratch...")
        qs = obj_class.objects.all()

    if qs.count() == 0:
        print("   - No %s-type items in the DB or none that have changed. All "
              "done here." % obj_type_str)
        history.mark_success_and_save()
        return 0
    else:
        if type(qs[0].pk) == int:
            item_list = queryset_generator(qs)
        else:
            # Necessary for Court objects, which don't have ints for ids.
            item_list = qs

        i = 0
        renderer = JSONRenderer()
        r = RequestFactory().request()
        r.META['SERVER_NAME'] = 'www.courtlistener.com'  # Else, it's testserver
        r.META['wsgi.url_scheme'] = 'https'  # Else, it's http.
        r.version = 'v3'
        r.versioning_scheme = URLPathVersioning()
        context = dict(request=r)
        for item in item_list:
            if i % 1000 == 0:
                print("Completed %s items so far." % i)
            json_str = renderer.render(
                serializer(item, context=context).data,
                accepted_media_type='application/json; indent=2',
            )

            if court_attr is not None:
                loc = join(bulk_dir, obj_type_str, deepgetattr(item, court_attr),
                           '%s.json' % item.pk)
            else:
                # A non-jurisdiction-centric object.
                loc = join(bulk_dir, obj_type_str, '%s.json' % item.pk)

            with open(loc, 'wb') as f:
                f.write(json_str)
            i += 1

        print ('   - %s %s json files created.' % (i, obj_type_str))

        history.mark_success_and_save()
        return i

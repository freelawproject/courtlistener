# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.alertSystem.models import Document
from optparse import OptionParser
import gc, errno, os, os.path, string, time

'''
This script finds all the documents that have PDF in their local_path field,
moves them to the correct pdf directory, then renames their extension so it's
pdf, not PDF.
'''

def queryset_iterator(queryset, chunksize=100):
    '''
    from: http://djangosnippets.org/snippets/1949/
    Iterate over a Django Queryset ordered by the primary key

    This method loads a maximum of chunksize (default: 1000) rows in its
    memory at the same time while django normally would load all rows in its
    memory. Using the iterator() method only causes it to not preload all the
    classes.

    Note that the implementation of the iterator does not support ordered query sets.
    '''
    documentUUID = 0
    last_pk = queryset.order_by('-documentUUID')[0].documentUUID
    queryset = queryset.order_by('documentUUID')
    while documentUUID < last_pk:
        for row in queryset.filter(documentUUID__gt=documentUUID)[:chunksize]:
            documentUUID = row.documentUUID
            yield row
        gc.collect()



def mkdir_p(path):
    # make a directory and its parents, if it doesn't exist
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST:
            pass
        else: raise


def update_new_path(doc):
    '''
    Iterate over ALL files, and check if their local_path field corresponds
    with a file in PDF. If so, move the file, assuming it doesn't create a
    collision.
    '''
    root = settings.MEDIA_ROOT
    new_path = str(doc.local_path)
    new_path_full = os.path.join(root, new_path)

    old_path_full = new_path_full.replace('pdf', 'PDF')
    print "Old Path: " + old_path_full

    # If the old path already exists, then it's a hit.
    # We need to move the file to a better location.
    if os.path.exists(old_path_full):
        print "Old path exists."
        # Before we move it, we need to check if we can move it to a new location
        # without a collision occuring.
        if os.path.exists(new_path_full):
            new_path_full = new_path_full + '_2'
            new_path = new_path + '_2'
            doc.local_path = new_path

            if os.path.exists(new_path_full):
                new_path_full = new_path_full[:-2] + '_3'
                new_path = new_path[:-2] + '_3'
                doc.local_path = new_path

                if os.path.exists(new_path_full):
                    new_path_full = new_path_full[:-2] + '_4'
                    new_path = new_path[:-2] + '_4'
                    doc.local_path = new_path

                    if os.path.exists(new_path_full):
                        print "Insane. The thing existed four times!"
                    exit(1)

    # Path existing problems are solved. Move the thing.
    print "Moving file to: " + new_path_full
    raw_input("Press any key to proceed.")
    os.rename(old_path_full, new_path_full)
    doc.save()


def update_path(doc):
    # Rename the path
    old_path = str(doc.local_path)
    new_path = old_path.replace('PDF', 'pdf')
    doc.local_path = new_path
    doc.save()

    # Move the file
    root = settings.MEDIA_ROOT
    old_path_full = os.path.join(root, old_path)
    new_path_full = os.path.join(root, new_path)

    # Check if the file already exists. Fix if so.
    if os.path.exists(new_path_full):
        # Problem. Fix it. Recursion would make this less terrible.
        new_path_full = new_path_full + '_2'
        new_path = new_path + '_2'
        doc.local_path = new_path
        doc.save()

        if os.path.exists(new_path_full):
            new_path_full = new_path_full[:-2] + '_3'
            new_path = new_path[:-2] + '_3'
            doc.local_path = new_path
            doc.save()

            if os.path.exists(new_path_full):
                new_path_full = new_path_full[:-2] + '_4'
                new_path = new_path[:-2] + '_4'
                doc.local_path = new_path
                doc.save()

                if os.path.exists(new_path_full):
                    print "Insane. The thing existed four times!"
                    exit(1)

    # Path existing problems are solved. Move the thing.
    os.rename(old_path_full, new_path_full)



def main():
    usage = "usage: %prog"
    parser = OptionParser(usage)
    (options, args) = parser.parse_args()

    # run the script across the entire DB
    queryset = queryset_iterator(Document.objects.all())
    for doc in queryset:
        update_new_path(doc)
    exit(0)



if __name__ == '__main__':
    main()

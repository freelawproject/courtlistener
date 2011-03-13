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


def update_path(doc, simulate):
    # Rename the path
    old_path = str(doc.local_path)
    new_path = old_path.replace('PDF', 'pdf')
    doc.local_path = new_path
    doc.save()

    # Move the file
    root = settings.MEDIA_ROOT
    old_path_full = os.path.join(root, old_path)
    new_path_full = os.path.join(root, new_path)

    if not simulate:
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




def update_date(doc, simulate):
    # take the doc, check its dateFiled field, make a hardlink to the PDF
    # location, and update the database
    if doc.dateFiled != None:
        dateFiled = doc.dateFiled
    else:
        # break from this function.
        print "\n***No dateFiled value for doc: " + str(doc.documentUUID) + ". Punting.***\n"
        return(1)
    if doc.local_path != "":
        local_path = doc.local_path
    else:
        print "\n***No local_path value for doc: " + str(doc.documentUUID) + ". Punting.***\n"
        return(2)
    root = settings.MEDIA_ROOT

    # old link
    old = os.path.join(root, str(local_path))

    # new link
    year, month, day = str(dateFiled).split("-")
    filename = os.path.basename(old)
    new = os.path.join(root, "pdf", year, month, day, filename)

    # make the new hard link if needed
    if old != new:
        if not simulate:
            mkdir_p(os.path.join(root, "pdf", year, month, day))
            try:
                os.link(old, new)
            except OSError as exc:
                if exc.errno == 17:
                    # Error 17: File exists. Append "2", and move on.
                    print "Duplicate file found, appending 2"
                    filename = filename[0:string.rfind(filename, ".")] + "2" \
                        + filename[string.rfind(filename, "."):]
		    new = os.path.join(root, "pdf", year, month, day, filename)
                    try:
			os.link(old, new)
		    except OSError as exc:
		        if exc.errno == 17:
			    print "Duplicate file found again, appending 3"
			    filename = filename[0:string.rfind(filename, ".")] + "3" \
			        + filename[string.rfind(filename, "."):]
		            new = os.path.join(root, "pdf", year, month, day, filename)
			    os.link(old, new)

            doc.local_path = os.path.join("pdf", year, month, day, filename)
            doc.save()
        print "***Created new hard link to " + new + " for doc: " + str(doc.documentUUID) + " ***"
    else:
        print 'Same. Not updating link for ' + str(doc.documentUUID)


def main():
    usage = "usage: %prog (-b BEGIN -e END) | -a [-s]"
    parser = OptionParser(usage)
    parser.add_option('-s', '--simulate', action="store_true", dest="simulate",
        default=False, help='Run the script in simulate mode. No changes will be made.')
    (options, args) = parser.parse_args()

    simulate = options.simulate

    if simulate:
        print '\n*****************************'
        print '* Running in simulate mode! *'
        print '*****************************\n'
        time.sleep(1)


    # run the script across the entire DB
    queryset = queryset_iterator(Document.objects.filter(local_path__endswith='PDF'))
    for doc in queryset:
        update_path(doc, simulate)
    exit(0)



if __name__ == '__main__':
    main()

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
import gc, errno, os, os.path, time

def queryset_iterator(queryset, chunksize=1000):
    '''''
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


def update_date(doc, simulate):
    time.sleep(1)
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
            os.link(old, new)
            doc.local_path = os.path.join("pdf", year, month, day, filename)
            doc.save()
        print "***Created new hard link to " + new + " for doc: " + str(doc.documentUUID) + " ***"
    else:
        print 'Same. Not updating link.'


def main():
    usage = "usage: %prog (-b BEGIN -e END) | -a [-s]"
    parser = OptionParser(usage)
    parser.add_option('-b', '--begin', dest='begin', metavar="BEGIN",
        help="The ID in the database where fixing should begin (inclusive).")
    parser.add_option('-e', '--end', dest='end', metavar="END",
        help="The ID in the database where fixing should end (inclusive).")
    parser.add_option('-a', '--all', action="store_true", dest='all',
        default=False, help='Run the script across the entire database ' + \
        '(use caution, as this is a resource intensive operation).')
    parser.add_option('-s', '--simulate', action="store_true", dest="simulate",
        default=False, help='Run the script in simulate mode. No changes will be made.')
    (options, args) = parser.parse_args()

    begin = options.begin
    end = options.end
    all = options.all
    simulate = options.simulate

    if not all:
        if not begin and not end:
            parser.error("You must specify either to parse all of the DB, or a starting and end point.")

    if simulate:
        print '\n*****************************'
        print '* Running in simulate mode! *'
        print '*****************************\n'
        time.sleep(1)

    if all:
        # run the script across the entire DB
        queryset = queryset_iterator(Document.objects.all())
        for doc in queryset:
            update_date(doc, simulate)
        exit(0)
    else:
        # run the script for the start and end points
        queryset = queryset_iterator(Document.objects.filter(documentUUID__gte=begin, documentUUID__lte=end))
        for doc in queryset:
            update_date(doc, simulate)
        exit(0)


if __name__ == '__main__':
    main()

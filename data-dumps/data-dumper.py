# -*- coding: utf-8 -*-

import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alertSystem.models import *

import gzip
import os
import time

from datetime import date
from lxml import etree
from optparse import OptionParser


def append_compressed_data(court_id, dump_dir, VERBOSITY):
    '''Dump the court's information to a file.

    Given a court ID and a verbosity, query the DB and dump the contents into
    an XML file. Compress the contents on the fly.
    '''

    if court_id == 0:
        # dump everything.
        docs_to_dump = Document.objects.all().order_by('court')
        court_id = 'all'
    else:
        # dump just the requested court
        court_id = PACER_CODES[court_id - 1][0]
        docs_to_dump = Document.objects.filter(court = court_id)

    # This var is needed to clear out null characters and control characters
    # (skipping newlines)
    null_map = dict.fromkeys(range(0,10) + range(11,13) + range(14,32))

    os.chdir(dump_dir)
    filename = 'latest-' + court_id + '.xml.gz.part'
    with gzip.open(filename, mode='wb') as z_file:
        z_file.write('<?xml version="1.0" encoding="utf-8"?>\n<opinions dumpdate="' + str(date.today()) + '">\n')

        for doc in docs_to_dump:
            row = etree.Element("opinion",
                dateFiled           = str(doc.dateFiled),
                precedentialStatus  = doc.documentType,
                local_path          = str(doc.local_path),
                time_retrieved      = str(doc.time_retrieved),
                download_URL        = doc.download_URL,
                caseNumber          = doc.citation.caseNumber,
                caseNameShort       = doc.citation.caseNameShort,
                court               = doc.court.get_courtUUID_display(),
                sha1                = doc.documentSHA1,
                source              = doc.get_source_display(),
                id                  = str(doc.documentUUID),
            )
            if doc.documentHTML != '':
                row.text = doc.documentHTML
            else:
                row.text = doc.documentPlainText.translate(null_map)
            z_file.write('  ' + etree.tostring(row).encode('utf-8') + '\n')

        # Close things off
        z_file.write('</opinions>')

        rotate_files(filename, VERBOSITY)


def rotate_files(filename, VERBOSITY):
    '''Rotates the dumps as needed.

    At most, 12 files are kept. Each month, latest-$court.gz is renamed to the
    correct month, then latest-court.gz.part is renamed as latest-$court.gz.

    This makes the process largely atomic - at no point is there an incomplete
    file that a user might download.

    Once that is renamed, any old dump is deleted. The dumps from January are
    always kept, but otherwise, all are deleted after 12 months.
    '''
    # This is hacky, but easier than dealing with timedeltas.
    year  = date.today().year
    month = date.today().month
    if month == 1:
        year_last_month = year - 1
        last_month = 12
    else:
        last_month = month -1
        year_last_month = year
    if VERBOSITY >= 3:
        print "month = %02d. year = %d" % (last_month, year_last_month)

    # Rename the latest files with the year and month of one month prior
    dump_files = os.listdir('.')
    for dump_file in dump_files:
        if dump_file == 'data-dumper.py':
            # Punt, or else we self-delete!
            continue
        elif dump_file == filename[0:-5]:
            # rename the file as appropriate, with zero-padded months
            if VERBOSITY >= 1:
                print "Renaming latest file: %s." % dump_file
            os.rename(dump_file, dump_file.replace('latest',
                '%d-%02d') % (year_last_month, last_month))
        elif dump_file == filename:
            # It's the file we just made a moment ago. Strip the .part from
            # its name.
            if VERBOSITY >= 1:
                print "Renaming " + filename + " as " + filename[0:-5]
            os.rename(filename, filename[0:-5])
        else:
            # Not a new file. See if it is more than a year old (and should be
            # deleted.
            creation_time = os.path.getctime(dump_file)
            now = time.time()
            difftime = now - creation_time
            if difftime > 31556926:
                # It's more than a year old. Was it made in a month other than
                # January?
                month_created = time.strftime('%m', time.gmtime(creation_time))
                if month_created != '01':
                    # Not from January. Delete it!
                    if VERBOSITY >= 1:
                        print dump_file + " is older than one year, and not " +
                            "made in January. Deleting."
                    os.unlink(dump_file)


def main():
    '''Dumps the database to compressed XML files.

    Uses django to dump the database into compressed XML files once a month. Can
    be called with the court as an argument (-c 1), in order to generate the
    dump for that court. If it is called with (-c 0), it will create a file for
    all courts (caution!)
    '''

    usage = "usage: %prog -c (courtID | all) -d DUMPDIR [-v VERBOSITY]"
    parser = OptionParser(usage)
    parser.add_option('-c', '--court', dest='court_id', metavar="COURTID",
        help="The court to dump")
    parser.add_option('-d', '--dumpdir', dest='dump_dir', metavar="DUMPDIR",
        help="The directory where data dumps should be created")
    parser.add_option('-v', '--verbosity', dest='verbosity', metavar="VERBOSITY",
        help="Display status messages during execution. Higher values print more verbosity.")
    (options, args) = parser.parse_args()

    try:
        VERBOSITY = int(options.verbosity)
    except:
        # No verbosity supplied
        VERBOSITY = 0
    try:
        court_id = int(options.court_id)
    except ValueError:
        parser.error("Court must be a valid integer")
    except TypeError:
        parser.error("Court is a required field")

    if options.dump_dir is None:
        parser.error("A dump directory must be specified.")
    elif not os.path.exists(options.dump_dir):
        # The directory doesn't exist.
        parser.error("Invalid dump directory. It may not exist, or you may not \
            have permission to access it.")
    else:
        dump_dir = options.dump_dir


    append_compressed_data(court_id, dump_dir, VERBOSITY)

    return 0


if __name__ == '__main__':
    main()




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

import calendar
import gzip
import shutil
import time
import os

from django.http import HttpResponseBadRequest

from datetime import date
from lxml import etree


class myGzipFile(gzip.GzipFile):
    '''Backports Python 2.7 functionality into 2.6.

    In order to use the 'with syntax' below, I need to subclass the gzip
    library here. Once all of the machines are running Python 2.7, this class
    can be removed, and the 'with' code below can simply reference the gzip
    class rather than this one.

    This line of code worked in 2.7:
    with gzip.open(filename, mode='wb') as z_file:
    '''
    def __enter__(self):
        if self.fileobj is None:
            raise ValueError("I/O operation on closed GzipFile object")
        return self

    def __exit__(self, *args):
        self.close()


def make_dump_file(docs_to_dump, path_from_root, filename):
    # This var is needed to clear out null characters and control characters
    # (skipping newlines)
    null_map = dict.fromkeys(range(0, 10) + range(11, 13) + range(14, 32))

    temp_dir = str(time.time())

    try:
        os.makedirs(os.path.join(path_from_root, temp_dir))
    except OSError:
        # Path exists.
        pass

    with myGzipFile(os.path.join(path_from_root, temp_dir, filename),
                    mode='wb') as z_file:

        z_file.write('<?xml version="1.0" encoding="utf-8"?>\n' +
                     '<opinions dumpdate="' + str(date.today()) + '">\n')

        try:
            for doc in docs_to_dump:
                row = etree.Element("opinion")
                try:
                    # These are required by the DB, and thus are safe
                    # without the try/except blocks
                    row.set('id', str(doc.documentUUID))
                    row.set('sha1', doc.documentSHA1)
                    row.set('court', doc.court.full_name)
                    row.set('download_URL', doc.download_URL)
                    row.set('time_retrieved', str(doc.time_retrieved))
                    try:
                        row.set('dateFiled', str(doc.dateFiled))
                    except:
                        # Value not found.
                        row.set('dateFiled', '')
                    try:
                        row.set('precedentialStatus', doc.documentType)
                    except:
                        # Value not found.
                        row.set('precedentialStatus', '')
                    try:
                        row.set('local_path', str(doc.local_path))
                    except:
                        # Value not found.
                        row.set('local_path', '')
                    try:
                        row.set('docketNumber', doc.citation.docketNumber)
                    except:
                        # Value not found.
                        row.set('docketNumber', '')
                    try:
                        row.set('westCite', doc.citation.westCite)
                    except:
                        # Value not found.
                        row.set('westCite', '')
                    try:
                        row.set('lexisCite', doc.citation.lexisCite)
                    except:
                        # Value not found.
                        row.set('lexisCite', '')
                    try:
                        row.set('case_name', doc.citation.case_name)
                    except:
                        # Value not found.
                        row.set('case_name', '')
                    try:
                        row.set('source', doc.get_source_display())
                    except:
                        # Value not found.
                        row.set('source', '')

                    # Gather the doc text
                    if doc.documentHTML != '':
                        row.text = doc.documentHTML
                    else:
                        row.text = doc.documentPlainText.translate(null_map)
                except ValueError:
                    # Null byte found. Punt.
                    continue

                z_file.write('  %s\n' % etree.tostring(row).encode('utf-8'))

        except IndexError:
            # Cleanup the temp files and exit. Ignore errors.
            shutil.rmtree(os.path.join(path_from_root, temp_dir), True)
            return HttpResponseBadRequest('<h2>Error 400: No cases found \
                for this time period.</h2>')


        # Close things off
        z_file.write('</opinions>')

    # Delete the old archive, then replace it with the new one. Deleting 
    # shouldn't necessary according to the Python documentation, but in testing
    # I'm not seeing file clobbering happen.
    try:
        os.remove(os.path.join(path_from_root, filename))
    except OSError:
        # The file doesn't exist yet. This should only really be triggered by
        # the all_cases dumper. The others shouldn't get this far.
        pass

    # Move the new file to the correct location
    os.rename(os.path.join(path_from_root, temp_dir, filename),
              os.path.join(path_from_root, filename) + '.gz')

    # Remove the directory, but only if it's empty. 
    os.rmdir(os.path.join(path_from_root, temp_dir))

    return os.path.join(path_from_root, filename)


def get_date_range(year, month, day):
    ''' Create a date range to be queried.

    Given a year and optionally a month or day, return a date range. If only a
    year is given, return start date of January 1, and end date of December
    31st. Do similarly if a year and month are supplied or if all three values
    are provided.
    '''
    # Sort out the start dates
    if month == None:
        start_month = 1
    else:
        start_month = int(month)
    if day == None:
        start_day = 1
    else:
        start_day = int(day)

    start_year = int(year)
    start_date = '%d-%02d-%02d' % (start_year, start_month, start_day)

    annual = False
    monthly = False
    daily = False
    # Sort out the end dates
    if day == None and month == None:
        # it's an annual query
        annual = True
        end_month = 12
        end_day = 31
    elif day == None:
        # it's a month query
        monthly = True
        end_month = int(month)
        end_day = calendar.monthrange(int(year), end_month)[1]
    else:
        # all three values provided!
        daily = True
        end_month = int(month)
        end_day = int(day)

    end_year = int(year)
    end_date = '%d-%02d-%02d' % (end_year, end_month, end_day)

    return start_date, end_date, annual, monthly, daily

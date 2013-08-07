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

        for doc in docs_to_dump:
            row = etree.Element("opinion")
            try:
                # These are required by the DB, and thus are safe
                # without the try/except blocks
                row.set('id', str(doc.documentUUID))
                row.set('path', doc.get_absolute_url())
                row.set('sha1', doc.sha1)
                row.set('court', doc.court.full_name)
                row.set('download_URL', doc.download_URL)
                row.set('time_retrieved', str(doc.time_retrieved))
                # All are wrapped in try/except b/c the value might not be found.
                try:
                    row.set('date_filed', str(doc.date_filed))
                except:
                    pass
                try:
                    row.set('precedential_status', doc.precedential_status)
                except:
                    pass
                try:
                    row.set('local_path', str(doc.local_path))
                except:
                    pass
                try:
                    row.set('docket_number', doc.citation.docket_number)
                except:
                    pass
                try:
                    row.set('federal_cite_one', doc.citation.federal_cite_one)
                except:
                    pass
                try:
                    row.set('federal_cite_two', doc.citation.federal_cite_two)
                except:
                    pass
                try:
                    row.set('federal_cite_three', doc.citation.federal_cite_three)
                except:
                    pass
                try:
                    row.set('state_cite_one', doc.citation.state_cite_one)
                except:
                    pass
                try:
                    row.set('state_cite_two', doc.citation.state_cite_two)
                except:
                    pass
                try:
                    row.set('state_cite_three', doc.citation.state_cite_three)
                except:
                    pass
                try:
                    row.set('state_cite_regional', doc.citation.state_cite_regional)
                except:
                    pass
                try:
                    row.set('specialty_cite_one', doc.citation.specialty_cite_one)
                except:
                    pass
                try:
                    row.set('scotus_early_cite', doc.citation.scotus_early_cite)
                except:
                    pass
                try:
                    row.set('lexis_cite', doc.citation.lexis_cite)
                except:
                    pass
                try:
                    row.set('westlaw_cite', doc.citation.westlaw_cite)
                except:
                    pass
                try:
                    row.set('neutral_cite', doc.citation.neutral_cite)
                except:
                    pass
                try:
                    row.set('case_name', doc.citation.case_name)
                except:
                    pass
                try:
                    row.set('judges', doc.judges)
                except:
                    pass
                try:
                    row.set('nature_of_suit', doc.nature_of_suit)
                except:
                    pass
                try:
                    row.set('source', doc.get_source_display())
                except:
                    pass
                try:
                    row.set('blocked', str(doc.blocked))
                except:
                    pass
                try:
                    row.set('date_blocked', str(doc.date_blocked))
                except:
                    pass
                try:
                    row.set('extracted_by_ocr', str(doc.extracted_by_ocr))
                except:
                    pass

                ids = ','.join([str(pk) for pk in doc.citation.citing_cases.all().values_list('pk', flat=True)])
                if len(ids) > 0:
                    row.set('cited_by', ids)

                # Gather the doc text
                if doc.html_with_citations:
                    row.text = doc.html_with_citations.translate(null_map)
                elif doc.html:
                    row.text = doc.html
                else:
                    row.text = doc.plain_text.translate(null_map)
            except ValueError:
                # Null byte found. Punt.
                continue

            z_file.write('  %s\n' % etree.tostring(row).encode('utf-8'))

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
    start_date = date(start_year, start_month, start_day)

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
    end_date = date(end_year, end_month, end_day)

    return start_date, end_date, annual, monthly, daily

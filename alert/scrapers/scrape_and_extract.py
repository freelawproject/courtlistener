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

#TODO: Use of the time.strptime function would improve this code here and there.
#   info here: http://docs.python.org/library/time.html#time.strptime

import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.lib.scrape_tools import court_changed
from alert.lib import magic
from alert.lib.string_utils import trunc
from alert.search.tasks import save_doc_handler
from alert.search.models import Citation
from alert.search.models import Document

from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from juriscraper.opinions.united_states.federal import *
from juriscraper.GenericSite import logger

# adding alert to the front of this breaks celery. Ignore pylint error.
from scrapers.tasks import extract_doc_content

import hashlib
import mimetypes
import signal
import time
import traceback
import urllib2
from optparse import OptionParser


# for use in catching the SIGINT (Ctrl+C)
die_now = False

def signal_handler(signal, frame):
    print 'Exiting safely...this will finish the current court, then exit...'
    global die_now
    die_now = True

def scrape_court(court, verbosity):
    try:
        site = court.Site().parse()
    except:
        #TODO: Print stack trace here.
        pass

    if not court_changed(site.url, site.hash):
        return
    else:
        logger.debug("Identified changed hash at: %s" % site.url)

    dup_count = 0
    for i in range(0, len(site.case_names)):
        # Percent encode URLs
        download_url = urllib2.quote(site.download_urls[i], safe="%/:=&?~#+!$,;'@()*[]")

        # TODO: Make this use a celery task with retries
        try:
            data = urllib2.urlopen(download_url).read()
            # test for empty files (thank you CA1)
            if len(data) == 0:
                err = "EmptyFileError: %s" % download_url
                logger.critical(traceback.format_exc())
        except:
            err = 'DownloadingError: %s' % download_url
            logger.critical(traceback.format_exc())

        # Make a hash of the file
        sha1_hash = hashlib.sha1(data).hexdigest()

        # using the hash, check for a duplicate in the db.
        # Turn of save signals since we don't want the document added to Solr 
        # until it's been parsed (at which time it happens automatically).
        post_save.disconnect(
                    save_doc_handler,
                    sender=Document,
                    dispatch_uid='save_doc_handler')
        doc, created = Document.objects.get_or_create(documentSHA1=sha1_hash)
        post_save.connect(
                    save_doc_handler,
                    sender=Document,
                    dispatch_uid='save_doc_handler')

        # If the doc is a dup, increment the dup_count variable and set the
        # dup_found_date
        if not created:
            dup_found_date = site.case_date[i]
            dup_count += 1
            continue
        else:
            dup_count = 0

        # opinions.united_states.federal.ca9u --> ca9 
        doc.court = site.court_id.split('.')[-1].strip('p').strip('u')
        doc.source = 'C'
        doc.dateFiled = site.case_dates[i]
        doc.documentType = site.statuses[i]
        doc.download_URL = download_url

        cf = ContentFile(data)
        mime = magic.from_buffer(data, mime=True)
        extension = mimetypes.guess_extension(mime)
        file_name = trunc(site.case_name[i], 80) + extension
        doc.local_path.save(file_name, cf, save=False)

        cite = Citation(case_name=site.case_names[i],
                        docketNumber=site.docket_numbers[i])
        cite.save()

        # Associate the cite with the doc
        doc.citation = cite
        doc.save()

        # Extract the contents asynchronously.
        extract_doc_content.delay(doc.pk)

        # If we found a dup on dup_found_date, then we can exit before 
        # parsing any prior dates.
        try:
            already_scraped_next_date = (site.case_dates[i + 1] < dup_found_date)
        except KeyError:
            already_scraped_next_date = True
        if already_scraped_next_date:
            return
        elif dup_count >= 5:
            return


def main():
    global die_now

    # this line is used for handling SIGINT, so things can die safely.
    signal.signal(signal.SIGQUIT, signal_handler)

    usage = 'usage: %prog -c COURTID [-d] [-r RATE] [-v {1,2}]'
    parser = OptionParser(usage)
    parser.add_option('-d', '--daemon', action="store_true", dest='daemonmode',
                      default=False, help=('Use this flag to turn on daemon '
                                           'mode, in which all courts will be '
                                           'sraped in turn, non-stop.'))
    parser.add_option('-r', '--rate', dest='rate', metavar='RATE',
                      help=('The length of time in minutes it takes to crawl all '
                            'known courts. Particularly useful if it is desired '
                            'to quickly scrape over all courts. Default is 30 '
                            'minutes.'))
    parser.add_option('-c', '--courts', dest='court_id', metavar="COURTID",
                      help=('The court(s) to scrape and extract. This should be in '
                            'the form of a python module or package import '
                            'from the Juriscraper library, e.g. '
                            '"opinions.united_states.federal.ca1" or '
                            'simply "opinions" to do everything.'))
    parser.add_option('-v', '--verbosity', dest='verbosity', metavar="VERBOSITY",
                      help=('Display status messages during execution. Higher '
                            'values print more verbosity.'))
    (options, args) = parser.parse_args()

    daemon_mode = options.daemonmode
    court_id = options.court_id

    if not court_id:
        parser.error('You must specify a court as a package or module.')
    else:
        try:
            import court_id
        except ImportError:
            parser.error('Unable to import court module or package.')

    try:
        verbosity = int(options.verbosity)
    except ValueError, AttributeError:
        verbosity = 0

    try:
        rate = int(options.rate)
    except ValueError, AttributeError:
        rate = 30
    num_courts = len(court_id.__all__)
    wait = (rate * 60) / num_courts
    i = 0
    while i >= num_courts:
        scrape_court(court_id.__all__[i], verbosity)
        # this catches SIGINT, so the code can be killed safely.
        if die_now == True:
            sys.exit(0)

        time.sleep(wait)
        if i == num_courts and daemon_mode:
            i = 0
        else:
            i += 1
    return 0

if __name__ == '__main__':
    main()

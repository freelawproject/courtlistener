"""This is a simple file that replicates/imports much of the current scraper's
functionality.

Some tricks that make it special:

1. It reads from a CSV.
1. It chooses the court based on a column in the CSV.
1. It cleans up the data like Juriscraper would normally do.
1. It inserts a delay after every item so as to save the server from
   exploding.

"""
from Queue import Queue
import hashlib
import os
import random
import sys
import threading
import traceback

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alert.settings")

from datetime import datetime
from django.core.files.base import ContentFile
from juriscraper.lib.string_utils import clean_string, harmonize

from alert.scrapers.management.commands.cl_scrape_opinions import \
    get_binary_content, get_extension
from juriscraper.AbstractSite import logger
from alert.audio.models import Audio
from alert.lib.string_utils import trunc
from alert.search.models import Court, Docket
from scrapers.tasks import process_audio_file


def make_line_to_dict(row):
    columns = row.split('\t')
    item = {
        'court_code':    columns[0],
        'docket_number': columns[1],
        'case_name':     columns[2],
        'url':           columns[3],
        'size':          columns[4],
        'counsel':       columns[5],
        'issues':        columns[6],
        'judges':        columns[7],
        'date_argued':   datetime.strptime(columns[8], '%Y-%m-%d').date(),
        'orig_url':      columns[9],
    }

    for key, value in item.iteritems():
        if key == 'url':
            item['url'] = value.strip()
        else:
            if isinstance(value, basestring):
                item[key] = clean_string(value)
                if key in ['case_name', 'docket_number']:
                    item[key] = harmonize(value)
    return item


def download_and_save():
    """This function is run in many threads simultaneously. Each thread
    runs so long as there are items in the queue. Once an item is found, it's
    downloaded and saved.

    The number of items that can be concurrently saved is determined by the
    number of threads that are running this function.
    """
    while True:
        item = queue.get()
        logger.info("%s: Attempting to add item at: %s" %
                    (threading.current_thread().name, item['url']))
        try:
            msg, r = get_binary_content(
                item['url'],
                {},
            )
        except:
            logger.info("%s: Unable to get item at: %s" %
                        (threading.current_thread().name, item['url']))
            queue.task_done()

        if msg:
            logger.warn(msg)
            queue.task_done()
            continue

        sha1_hash = hashlib.sha1(r.content).hexdigest()
        if Audio.objects.filter(sha1=sha1_hash).exists():
            # Simpsons did it! Try the next one.
            logger.info("%s: Item already exists, moving to next item." %
                        threading.current_thread().name)
            queue.task_done()
            continue
        else:
            # New item, onwards!
            logger.info('%s: Adding new document found at: %s' %
                        (threading.current_thread().name, item['url']))
            audio_file = Audio(
                source='H',
                sha1=sha1_hash,
                case_name=item['case_name'],
                date_argued=item['date_argued'],
                download_url=item['url'],
                processing_complete=False,
            )
            if item['judges']:
                audio_file.judges = item['judges']
            if item['docket_number']:
                audio_file.docket_number = item['docket_number']

            court = Court.objects.get(pk=item['court_code'])

            docket = Docket(
                case_name=item['case_name'],
                court=court,
            )
            # Make and associate the file object
            try:
                cf = ContentFile(r.content)
                extension = get_extension(r.content)
                if extension not in ['.mp3', '.wma']:
                    extension = '.' + item['url'].rsplit('.', 1)[1]
                # See bitbucket issue #215 for why this must be
                # lower-cased.
                file_name = trunc(item['case_name'].lower(), 75) + extension
                audio_file.local_path_original_file.save(file_name, cf,
                                                         save=False)
            except:
                msg = 'Unable to save binary. Deleted document: %s.\n%s' % \
                      (item['case_name'], traceback.format_exc())
                logger.critical(msg)
                queue.task_done()

            docket.save()
            audio_file.docket = docket
            audio_file.save(index=False)

            random_delay = random.randint(0, 3600)
            process_audio_file.apply_async(
                (audio_file.pk,),
                countdown=random_delay
            )

            logger.info("%s: Successfully added audio file %s: %s" %
                        (threading.current_thread().name,
                         audio_file.pk,
                         audio_file.case_name))


concurrent_threads = 8
queue = Queue(concurrent_threads * 2)

if __name__ == '__main__':
    logger.info('Creating %s threads.' % concurrent_threads)
    for _ in range(concurrent_threads):
        t = threading.Thread(target=download_and_save)
        t.daemon = True
        t.start()
    logger.info('All threads created and started.')

    with open('arguments-from-brad-heath-shuffled.csv', 'r') as csv:
        next(csv)  # Skip the first line
        for row in csv:
            item = make_line_to_dict(row)
            queue.put(item)

    # Block completion of this function until the queue is empty.
    try:
        queue.join()
        logger.info("%s: Successfully crawled oral arguments from BH archive.")
    except KeyboardInterrupt:
        sys.exit()

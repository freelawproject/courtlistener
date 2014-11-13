"""This is a simple file that replicates/imports much of the current scraper's
functionality.

Some tricks that make it special:

1. It reads from a CSV.
1. It chooses the court based on a column in the CSV.
1. It cleans up the data like Juriscraper would normally do.
1. It inserts a delay after every item so as to save the server from
   exploding.

"""
import hashlib
import os
import random
import sys
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


with open('arguments-from-brad-heath.csv', 'r') as csv:
    next(csv)  # Skip the first line
    for row in csv:
        logger.info("Attempting to add item at: %s" % item['url'])
        item = make_line_to_dict(row)
        try:
            msg, r = get_binary_content(
                item['url'],
                {},
            )
        except:
            logger.info("Unable to get item at: %s" % item['url'])

        if msg:
            logger.warn(msg)
            continue

        sha1_hash = hashlib.sha1(r.content).hexdigest()
        if Audio.objects.filter(sha1=sha1_hash).exists():
            # Simpsons did it! Try the next one.
            logger.info("Item already exists, moving to next item.")
            continue
        else:
            # New item, onwards!
            logger.info('Adding new document found at: %s' % item['url'])
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
                if extension not in ['mp3', 'wma']:
                    extension = item['url'].rsplit('.', 1)[1]
                # See bitbucket issue #215 for why this must be
                # lower-cased.
                file_name = trunc(item['case_name'].lower(), 75) + extension
                audio_file.local_path_original_file.save(file_name, cf,
                                                         save=False)
            except:
                msg = 'Unable to save binary to disk. Deleted document: % s.\n % s' % \
                      (item['case_name'], traceback.format_exc())
                logger.critical(msg)
                continue

            docket.save()
            audio_file.docket = docket
            audio_file.save(index=False)

            random_delay = random.randint(0, 3600)
            process_audio_file.apply_async(
                (audio_file.pk,),
                countdown=random_delay
            )

            logger.info("Successfully added audio file %s: %s" % (
                audio_file.pk, audio_file.case_name))

    logger.info("%s: Successfully crawled oral arguments from BH archive.")

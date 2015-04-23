"""See more details at:

https://github.com/freelawproject/courtlistener/issues/311

The process will be to iterate over the oral arguments that were part of the
Brad Heath import and to use the download URL as our anchor when fixing
everything.


1. Import a fresh copy of the CSV and store it in a data structure that makes
   it possible to look up items by download URL.

1. For each item in the brad heath collection:
     - use the download URL to look up the correct meta data
     - create a new audio item using the original mp3 on disk, the local mp3 on
       disk and the correct meta data.
     - create a new docket to go with that item or update the original docket.
     - update the ID3 data for the mp3.
     - delete:
        - the old Audio item
        - the original files associated with it (both of them).
        - the docket associated with it.

1. Wait for or manually send a commit to Solr.
"""
import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alert.settings")

from django.core.files.base import ContentFile
from alert.audio.models import Audio
from alert.corpus_importer.brad_heath_oral_arguments.import_oa_from_csv \
    import make_line_to_dict
from alert.lib.string_utils import trunc
from alert.scrapers.tasks import set_mp3_meta_data
from alert.search.models import Court
from juriscraper.AbstractSite import logger


if __name__ == '__main__':
    logger.info("Updating all items part of Brad Heath collection")

    csv = {}
    with open('arguments-from-brad-heath-untouched.csv', 'r') as f:
        # Import a fresh copy of the CSV and store it so we can look things up
        # by URL.
        next(f)
        for row in f:
            item_dict = make_line_to_dict(row)
            csv[item_dict['url']] = item_dict

    for af in Audio.objects.filter(source='H').order_by('time_retrieved'):
        # For every item in the BH archive...
        logger.info("Updating item %s with URL: %s" %
                    (af.pk, af.download_url))

        # sha1_hash --> OK, unchanged.
        # download_url --> OK, unchanged.

        item = csv[af.download_url]
        docket = af.docket

        af.case_name = item['case_name']
        docket.case_name = item['case_name']
        af.date_argued = item['date_argued']

        if item['judges']:
            af.judges = item['judges']
        if item['docket_number']:
            af.docket.docket_number = item['docket_number']

        court = Court.objects.get(pk=item['court_code'])
        docket.court = court

        # Fix the files. First save the location of the old files.
        original_local_path = af.local_path_original_file.path
        original_mp3_path = af.local_path_mp3.path

        # Create a new file with the contents of the old and a corrected
        # name. This is only in memory for the moment.
        cf = ContentFile(af.local_path_original_file.read())
        extension = '.' + af.local_path_original_file.path.rsplit('.', 1)[1]
        file_name = trunc(item['case_name'].lower(), 75) + extension
        af.local_path_original_file.save(file_name, cf, save=False)

        # Create a new mp3 file with the new contents
        cf = ContentFile(af.local_path_mp3.read())
        file_name = trunc(af.case_name.lower(), 72) + '_cl.mp3'
        af.local_path_mp3.save(file_name, cf, save=False)

        # Save things so they can be referenced in a sec.
        docket.save()
        af.save(index=False)

        # Update the ID3 information and duration data.
        new_mp3_path = af.local_path_mp3.path
        logger.info("Updating mpr at: %s" % new_mp3_path)
        set_mp3_meta_data(af, new_mp3_path)

        docket.save()
        af.save(index=True)

        os.remove(original_local_path)
        os.remove(original_mp3_path)

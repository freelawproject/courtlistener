# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import subprocess
import traceback
import uuid

import eyed3
from django.conf import settings
from django.core.files.base import ContentFile
from eyed3 import id3
from seal_rookery import seals_data, seals_root

from cl.audio.models import Audio
from cl.audio.utils import get_audio_binary
from cl.celery import app
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.document_processors import make_pdftotext_process, \
    extract_by_ocr
from cl.lib.recap_utils import needs_ocr
from cl.lib.string_utils import anonymize, trunc
from cl.lib.utils import is_iter
from cl.scrapers.models import ErrorLog
from cl.search.models import RECAPDocument


@app.task
def extract_recap_pdf(pks, skip_ocr=False, check_if_needed=True):
    """Extract the contents from a RECAP PDF if necessary."""
    if not is_iter(pks):
        pks = [pks]

    processed = []
    for pk in pks:
        rd = RECAPDocument.objects.get(pk=pk)
        if check_if_needed and not rd.needs_extraction:
            # Early abort if the item doesn't need extraction and the user
            # hasn't disabled early abortion.
            processed.append(pk)
            continue
        path = rd.filepath_local.path
        process = make_pdftotext_process(path)
        content, err = process.communicate()
        content = content.decode('utf-8', errors='ignore')

        if needs_ocr(content):
            if not skip_ocr:
                # probably an image PDF. Send it to OCR.
                success, content = extract_by_ocr(path)
                if success:
                    rd.ocr_status = RECAPDocument.OCR_COMPLETE
                elif content == u'' or not success:
                    content = u'Unable to extract document content.'
                    rd.ocr_status = RECAPDocument.OCR_FAILED
            else:
                content = u''
                rd.ocr_status = RECAPDocument.OCR_NEEDED
        else:
            rd.ocr_status = RECAPDocument.OCR_UNNECESSARY

        rd.plain_text, _ = anonymize(content)
        # Do not do indexing here. Creates race condition in celery.
        rd.save(index=False, do_extraction=False)
        processed.append(pk)

    return processed


def set_mp3_meta_data(audio_obj, mp3_path):
    """Sets the meta data on the mp3 file to good values.

    :param audio_obj: an Audio object to clean up.
    :param mp3_path: the path to the mp3 to be converted.
    """
    court = audio_obj.docket.court

    # Load the file, delete the old tags and create a new one.
    audio_file = eyed3.load(mp3_path)

    # Undocumented API from eyed3.plugins.classic.ClassicPlugin#handleRemoves
    id3.Tag.remove(
        audio_file.tag.file_info.name,
        id3.ID3_ANY_VERSION,
        preserve_file_time=False,
    )
    audio_file.initTag()
    audio_file.tag.title = best_case_name(audio_obj)
    audio_file.tag.album = u'{court}, {year}'.format(
        court=court.full_name,
        year=audio_obj.docket.date_argued.year
    )
    audio_file.tag.artist = court.full_name
    audio_file.tag.artist_url = court.url
    audio_file.tag.audio_source_url = audio_obj.download_url
    audio_file.tag.comments.set(
        u'Argued: {date_argued}. Docket number: {docket_number}'.format(
            date_argued=audio_obj.docket.date_argued.strftime('%Y-%m-%d'),
            docket_number=audio_obj.docket.docket_number,
        ))
    audio_file.tag.genre = u'Speech'
    audio_file.tag.publisher = u'Free Law Project'
    audio_file.tag.publisher_url = u'https://free.law'
    audio_file.tag.recording_date = audio_obj.docket.date_argued.strftime('%Y-%m-%d')

    # Add images to the mp3. If it has a seal, use that for the Front Cover
    # and use the FLP logo for the Publisher Logo. If it lacks a seal, use the
    # Publisher logo for both the front cover and the Publisher logo.
    try:
        has_seal = seals_data[court.pk]['has_seal']
    except AttributeError:
        # Unknown court in Seal Rookery.
        has_seal = False
    except KeyError:
        # Unknown court altogether (perhaps a test?)
        has_seal = False

    flp_image_frames = [
        3,   # "Front Cover". Complete list at eyed3/id3/frames.py
        14,  # "Publisher logo".
    ]
    if has_seal:
        with open(os.path.join(seals_root,
                               '512', '%s.png' % court.pk), 'r') as f:
            audio_file.tag.images.set(
                3,
                f.read(),
                'image/png',
                u'Seal for %s' % court.short_name,
            )
        flp_image_frames.remove(3)

    for frame in flp_image_frames:
        with open(os.path.join(settings.INSTALL_ROOT,
                               'cl', 'audio', 'static', 'png',
                               'producer-300x300.png'), 'r') as f:
            audio_file.tag.images.set(
                frame,
                f.read(),
                'image/png',
                u'Created for the public domain by Free Law Project',
            )

    audio_file.tag.save()


@app.task
def process_audio_file(pk):
    """Given the key to an audio file, extract its content and add the related
    meta data to the database.
    """
    af = Audio.objects.get(pk=pk)
    tmp_path = os.path.join('/tmp', 'audio_' + uuid.uuid4().hex + '.mp3')
    av_path = get_audio_binary()
    av_command = [
        av_path, '-i', af.local_path_original_file.path,
        '-ar', '22050',  # sample rate (audio samples/s) of 22050Hz
        '-ab', '48k',    # constant bit rate (sample resolution) of 48kbps
        tmp_path
    ]
    try:
        _ = subprocess.check_output(av_command, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print('%s failed command: %s\nerror code: %s\noutput: %s\n%s' %
              (av_path, av_command, e.returncode, e.output,
               traceback.format_exc()))
        raise

    set_mp3_meta_data(af, tmp_path)
    try:
        with open(tmp_path, 'r') as mp3:
            cf = ContentFile(mp3.read())
            file_name = trunc(best_case_name(af).lower(), 72) + '_cl.mp3'
            af.file_with_date = af.docket.date_argued
            af.local_path_mp3.save(file_name, cf, save=False)
    except:
        msg = ("Unable to save mp3 to audio_file in scraper.tasks."
               "process_audio_file for item: %s\n"
               "Traceback:\n"
               "%s" % (af.pk, traceback.format_exc()))
        print(msg)
        ErrorLog.objects.create(log_level='CRITICAL', court=af.docket.court,
                                message=msg)

    af.duration = eyed3.load(tmp_path).info.time_secs
    af.processing_complete = True
    af.save()

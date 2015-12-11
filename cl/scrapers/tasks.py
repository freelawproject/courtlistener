# -*- coding: utf-8 -*-
from cl.audio.models import Audio
from cl.citations.tasks import update_document_by_id
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.string_utils import anonymize, trunc
from cl.lib.mojibake import fix_mojibake
from cl.scrapers.models import ErrorLog
from cl.search.models import Opinion
from celery import task
from celery.task.sets import subtask
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.encoding import smart_text, DjangoUnicodeDecodeError
from django.utils.timezone import now
from lxml.html.clean import Cleaner
from lxml.etree import XMLSyntaxError
from seal_rookery import seals_data, seals_root

import os
import eyed3
import glob
import subprocess
import time
import traceback


DEVNULL = open('/dev/null', 'w')


def get_clean_body_content(content):
    """Parse out the body from an html string, clean it up, and send it along.
    """
    cleaner = Cleaner(style=True,
                      remove_tags=['a', 'body', 'font', 'noscript', 'img'])
    try:
        return cleaner.clean_html(content)
    except XMLSyntaxError:
        return "Unable to extract the content from this file. Please try " \
               "reading the original."


def extract_from_doc(path, DEVNULL):
    """Extract text from docs.

    We use antiword to pull the text out of MS Doc files.
    """
    process = subprocess.Popen(['antiword', path, '-i', '1'], shell=False,
                               stdout=subprocess.PIPE, stderr=DEVNULL)
    content, err = process.communicate()
    return content, err


def extract_from_html(path):
    """Extract from html.

    A simple wrapper to go get content, and send it along.
    """
    try:
        content = open(path).read()
        content = get_clean_body_content(content)
        err = False
    except:
        content = ''
        err = True
    return content, err


def extract_from_pdf(doc, path, DEVNULL, callback=None):
    """ Extract text from pdfs.

    Here, we use pdftotext. If that fails, try to use tesseract under the
    assumption it's an image-based PDF. Once that is complete, we check for the
    letter e in our content. If it's not there, we try to fix the mojibake
    that ca9 sometimes creates.
    """
    process = subprocess.Popen(
        ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
        shell=False,
        stdout=subprocess.PIPE,
        stderr=DEVNULL
    )
    content, err = process.communicate()
    if content.strip() == '' and callback:
        # probably an image PDF. Send it to OCR
        result = subtask(callback).delay(path)
        success, content = result.get()
        if success:
            doc.extracted_by_ocr = True
        elif content == '' or not success:
            content = 'Unable to extract document content.'
    elif 'e' not in content:
        # It's a corrupt PDF from ca9. Fix it.
        content = fix_mojibake(unicode(content, 'utf-8', errors='ignore'))

    return doc, content, err


def extract_from_txt(path):
    """Extract text from plain text files: A fool's errand.

    Unfortunately, plain text files lack encoding information, so we have to
    guess. We could guess ascii, but we may as well use a superset of ascii,
    cp1252, and failing that try utf-8, ignoring errors. Most txt files we
    encounter were produced by converting wpd or doc files to txt on a
    Microsoft box, so assuming cp1252 as our first guess makes sense.

    May we hope for a better world.
    """
    try:
        err = False
        data = open(path).read()
        try:
            # Alas, cp1252 is probably still more popular than utf-8.
            content = smart_text(data, encoding='cp1252')
        except DjangoUnicodeDecodeError:
            content = smart_text(data, encoding='utf-8', errors='ignore')
    except:
        err = True
        content = ''
    return content, err


def extract_from_wpd(opinion, path, DEVNULL):
    """Extract text from a Word Perfect file

    Yes, courts still use these, so we extract their text using wpd2html. Once
    that's done, we pull out the body of the HTML, and do some minor cleanup
    on it.
    """
    process = subprocess.Popen(['wpd2html', path], shell=False,
                               stdout=subprocess.PIPE, stderr=DEVNULL)
    content, err = process.communicate()

    content = get_clean_body_content(content)

    if 'not for publication' in content.lower():
        opinion.precedential_status = "Unpublished"

    return opinion, content, err


@task
def extract_doc_content(pk, callback=None, citation_countdown=0):
    """
    Given a document, we extract it, sniffing its extension, then store its
    contents in the database.  Finally, we asynchronously find citations in
    the document content and match them to other documents.

    TODO: this implementation cannot be distributed due to using local paths.
    """
    opinion = Opinion.objects.get(pk=pk)

    path = opinion.local_path.path

    extension = path.split('.')[-1]
    if extension == 'doc':
        content, err = extract_from_doc(path, DEVNULL)
    elif extension == 'html':
        content, err = extract_from_html(path)
    elif extension == 'pdf':
        opinion, content, err = extract_from_pdf(opinion, path, DEVNULL, callback)
    elif extension == 'txt':
        content, err = extract_from_txt(path)
    elif extension == 'wpd':
        opinion, content, err = extract_from_wpd(opinion, path, DEVNULL)
    else:
        print ('*****Unable to extract content due to unknown extension: %s '
               'on opinion: %s****' % (extension, opinion))
        return 2

    if extension in ['html', 'wpd']:
        opinion.html, blocked = anonymize(content)
    else:
        opinion.plain_text, blocked = anonymize(content)

    if blocked:
        opinion.cluster.blocked = True
        opinion.cluster.date_blocked = now()

    if err:
        print ("****Error extracting text from %s: %s****" %
               (extension, opinion))
        return opinion

    try:
        if citation_countdown == 0:
            # No waiting around. Save to the database now, but don't bother
            # with the index yet because citations are being done imminently.
            opinion.cluster.save(index=False)
            opinion.save(index=False)
        else:
            # Save to the index now, citations come later, commit comes
            # according to schedule
            opinion.cluster.save(index=False)
            opinion.save(index=True)
    except Exception, e:
        print "****Error saving text to the db for: %s****" % opinion
        print traceback.format_exc()
        return opinion

    # Identify and link citations within the document content
    update_document_by_id.apply_async(
        (opinion.pk,),
        countdown=citation_countdown
    )

    return opinion


def convert_to_pngs(path, tmp_file_prefix):
    image_magick_command = ['convert', '-depth', '4', '-density', '300',
                            '-background', 'white', '+matte', path,
                            '%s.png' % tmp_file_prefix]
    magick_out = subprocess.check_output(image_magick_command,
                                         stderr=subprocess.STDOUT)
    return magick_out


def convert_to_txt(tmp_file_prefix):
    tess_out = ''
    for png in sorted(glob.glob('%s*' % tmp_file_prefix)):
        tesseract_command = ['tesseract', png, png[:-4], '-l', 'eng']
        tess_out = subprocess.check_output(
            tesseract_command,
            stderr=subprocess.STDOUT
        )
    return tess_out


@task
def extract_by_ocr(path):
    """Extract the contents of a PDF using OCR

    Convert the PDF to a collection of png's, then perform OCR using Tesseract.
    Take the contents and the exit code and return them to the caller.
    """
    content = ''
    success = False
    try:
        tmp_file_prefix = os.path.join('/tmp', str(time.time()))
        fail_msg = ("Unable to extract the content from this file. Please try "
                    "reading the original.")
        try:
            convert_to_pngs(path, tmp_file_prefix)
        except subprocess.CalledProcessError:
            content = fail_msg
            success = False

        try:
            convert_to_txt(tmp_file_prefix)
        except subprocess.CalledProcessError:
            # All is lost.
            content = fail_msg
            success = False

        try:
            for txt_file in sorted(glob.glob('%s*' % tmp_file_prefix)):
                if 'txt' in txt_file:
                    content += open(txt_file).read()
            success = True
        except IOError:
            print ("OCR was unable to finish due to not having a txt file "
                   "created. This usually happens when Tesseract cannot "
                   "ingest the file created for the pdf at: %s" % path)
            content = fail_msg
            success = False

    finally:
        # Remove tmp_file and the text file
        for f in glob.glob('%s*' % tmp_file_prefix):
            try:
                os.remove(f)
            except OSError:
                pass

    return success, content


def set_mp3_meta_data(audio_obj, mp3_path):
    """Sets the meta data on the mp3 file to good values.

    :param audio_obj: an Audio object to clean up.
    :param mp3_path: the path to the mp3 to be converted.
    """
    court = audio_obj.docket.court

    # Nuke the old id3 tags.
    eyed3_command = [
        'eyeD3',
        '--remove-all',
        '--quiet',
        mp3_path,
    ]
    try:
        _ = subprocess.check_output(
            eyed3_command,
            stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError, e:
        print 'eyeD3 failed command: %s\nerror code: %s\noutput: %s\n' % \
              (eyed3_command, e.returncode, e.output)
        print traceback.format_exc()
        raise

    # Load the file, then create a fresh tag.
    audio_file = eyed3.load(mp3_path)
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
    audio_file.tag.publisher_url = u'http://www.freelawproject.org'
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
                               'producer.png'), 'r') as f:
            audio_file.tag.images.set(
                frame,
                f.read(),
                'image/png',
                u'Created for the public domain by Free Law Project',
            )

    audio_file.tag.save()


@task
def process_audio_file(pk):
    """Given the key to an audio file, extract its content and add the related
    meta data to the database.
    """
    af = Audio.objects.get(pk=pk)
    path_to_original = af.local_path_original_file.path

    path_to_tmp_location = os.path.join('/tmp', str(time.time()) + '.mp3')

    # Convert original file to:
    #  - mono (-ac 1)
    #  - sample rate (audio samples / s) of 22050Hz (-ar 22050)
    #  - constant bit rate (sample resolution) of 48kbps (-ab 48k)
    avconv_command = ['avconv', '-i', path_to_original,
                      '-ac', '1',
                      '-ar', '22050',
                      '-ab', '48k',
                      path_to_tmp_location]
    try:
        _ = subprocess.check_output(
            avconv_command,
            stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError, e:
        print 'avconv failed command: %s\nerror code: %s\noutput: %s\n' % \
              (avconv_command, e.returncode, e.output)
        print traceback.format_exc()
        raise

    # Have to do this last because otherwise the mp3 hasn't yet been generated.
    set_mp3_meta_data(af, path_to_tmp_location)

    af.duration = eyed3.load(path_to_tmp_location).info.time_secs

    with open(path_to_tmp_location, 'r') as mp3:
        try:
            cf = ContentFile(mp3.read())
            file_name = trunc(best_case_name(af).lower(), 72) + '_cl.mp3'
            af.file_with_date = af.docket.date_argued
            af.local_path_mp3.save(file_name, cf, save=False)
        except:
            msg = "Unable to save mp3 to audio_file in scraper.tasks.process_" \
                  "audio_file for item: %s\nTraceback:\n%s" % \
                  (af.pk, traceback.format_exc())
            print msg
            ErrorLog(log_level='CRITICAL', court=af.docket.court,
                     message=msg).save()

    af.processing_complete = True
    af.save()
    os.remove(path_to_tmp_location)

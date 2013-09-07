# -*- coding: utf-8 -*-

import sys

sys.path.append('/var/www/court-listener/alert')

from alert import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.search.models import Document
from alert.lib.string_utils import anonymize
from alert.lib.mojibake import fix_mojibake
from celery.decorators import task
from celery.task.sets import subtask
from datetime import date
from lxml.html.clean import Cleaner
from lxml.etree import XMLSyntaxError

# adding alert to the front of this breaks celery. Ignore pylint error.
from citations.tasks import update_document_by_id

import glob
import os
import subprocess
import time
import traceback


def get_clean_body_content(content):
    """Parse out the body from an html string, clean it up, and send it along.
    """
    cleaner = Cleaner(style=True,
                      remove_tags=['a', 'body', 'font', 'noscript'])
    try:
        return cleaner.clean_html(content)
    except XMLSyntaxError:
        return "Unable to extract the content from this file. Please try reading the original."


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
    process = subprocess.Popen(["pdftotext", "-layout", "-enc", "UTF-8",
        path, "-"], shell=False, stdout=subprocess.PIPE, stderr=DEVNULL)
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
    """Extract text from plain text files.

    This function is really here just for consistency.
    """
    try:
        content = open(path).read()
        err = False
    except:
        err = True
    return content, err


def extract_from_wpd(doc, path, DEVNULL):
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
        doc.precedential_status = "Unpublished"

    return doc, content, err


@task
def extract_doc_content(pk, callback=None):
    """
    Given a document, we extract it, sniffing its extension, then store its
    contents in the database.  Finally, we asynchronously find citations in
    the document content and match them to other documents.

    TODO: this implementation cannot be distributed due to using local paths.
    """
    doc = Document.objects.get(pk=pk)

    path = str(doc.local_path)
    path = os.path.join(settings.MEDIA_ROOT, path)

    DEVNULL = open('/dev/null', 'w')
    extension = path.split('.')[-1]
    if extension == 'doc':
        content, err = extract_from_doc(path, DEVNULL)
    elif extension == 'html':
        content, err = extract_from_html(path)
    elif extension == 'pdf':
        doc, content, err = extract_from_pdf(doc, path, DEVNULL, callback)
    elif extension == 'txt':
        content, err = extract_from_txt(path)
    elif extension == 'wpd':
        doc, content, err = extract_from_wpd(doc, path, DEVNULL)
    else:
        print ('*****Unable to extract content due to unknown extension: %s '
               'on doc: %s****' % (extension, doc))
        return 2

    if extension in ['html', 'wpd']:
        doc.html, blocked = anonymize(content)
    else:
        doc.plain_text, blocked = anonymize(content)

    if blocked:
        doc.blocked = True
        doc.date_blocked = date.today()

    if err:
        print "****Error extracting text from %s: %s****" % (extension, doc)
        return doc

    try:
        doc.save(index=False)
    except Exception, e:
        print "****Error saving text to the db for: %s****" % doc
        print traceback.format_exc()
        return doc

    # Identify and link citations within the document content
    update_document_by_id.delay(doc.pk)

    return doc


def convert_to_tiff(path, tmp_file_prefix):
    image_magick_command = ['convert', '-depth', '4', '-density', '300',
                            '-background', 'white', '+matte', path,
                            '%s.tiff' % tmp_file_prefix]
    magick_out = subprocess.check_output(image_magick_command,
                                         stderr=subprocess.STDOUT)
    return magick_out


def convert_to_pngs(path, tmp_file_prefix):
    image_magick_command = ['convert', '-depth', '4', '-density', '300',
                            '-background', 'white', '+matte', path,
                            '%s.png' % tmp_file_prefix]
    magick_out = subprocess.check_output(image_magick_command,
                                         stderr=subprocess.STDOUT)
    return magick_out


def convert_to_txt(tmp_file_prefix, image_type):
    if image_type == 'tiffs':
        tesseract_command = ['tesseract', '%s.tiff' % tmp_file_prefix,
                             tmp_file_prefix, '-l', 'eng']
        tess_out = subprocess.check_output(tesseract_command,
                                           stderr=subprocess.STDOUT)
    elif image_type == 'pngs':
        for png in sorted(glob.glob('%s*' % tmp_file_prefix)):
            if 'tiff' not in png:
                tesseract_command = ['tesseract', png, png[:-4], '-l', 'eng']
                tess_out = subprocess.check_output(tesseract_command,
                                                   stderr=subprocess.STDOUT)
    return tess_out


@task
def extract_by_ocr(path):
    """Extract the contents of a PDF using OCR

    Convert the PDF to a tiff, then perform OCR on the tiff using Tesseract.
    Take the contents and the exit code and return them to the caller.
    """
    content = ''
    success = False
    image_type = 'tiffs'
    try:
        # The logic here is to try doing OCR with tiffs, and to fall back to
        # pngs if necessary. Depending on how each step goes, we either
        # proceed or abort.
        tmp_file_prefix = os.path.join('/tmp', str(time.time()))
        fail_msg = "Unable to extract the content from this file. Please try reading the original."
        try:
            convert_to_tiff(path, tmp_file_prefix)
        except subprocess.CalledProcessError:
            try:
                convert_to_pngs(path, tmp_file_prefix)
                image_type = 'pngs'
            except subprocess.CalledProcessError:
                content = fail_msg
                success = False

        try:
            convert_to_txt(tmp_file_prefix, image_type)
        except subprocess.CalledProcessError:
            if image_type == 'tiffs':
                # We haven't tried pngs yet, try them.
                try:
                    convert_to_pngs(path, tmp_file_prefix)
                    image_type = 'pngs'
                except subprocess.CalledProcessError:
                    # All is lost.
                    content = fail_msg
                    success = False
                try:
                    convert_to_txt(tmp_file_prefix, image_type)
                except subprocess.CalledProcessError:
                    # All is lost.
                    content = fail_msg
                    success = False

        try:
            if image_type == 'tiffs':
                content = open('%s.txt' % tmp_file_prefix).read()
            elif image_type == 'pngs':
                for txt_file in sorted(glob.glob('%s*' % tmp_file_prefix)):
                    if 'txt' in txt_file:
                        content += open(txt_file).read()
            success = True
        except IOError:
            print ("OCR was unable to finish due to not having a txt file created. "
                   "This usually happens when Tesseract cannot ingest the tiff file at: %" % path)
            content = fail_msg
            success = False

    finally:
        # Remove tmp_file and the text file
        for suffix in ['.tiff', '.txt']:
            try:
                os.remove(tmp_file_prefix + suffix)
            except OSError:
                pass

    return success, content

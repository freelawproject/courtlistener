# -*- coding: utf-8 -*-

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
from juriscraper.GenericSite import logger
from lxml import etree
from lxml.etree import tostring

# adding alert to the front of this breaks celery. Ignore pylint error.
from citations.tasks import update_document_by_id

import os
import re
import StringIO
import subprocess
import time
import traceback


def get_clean_body_content(content):
    '''Parse out the body from an html string, clean it up, and send it along.
    '''
    parser = etree.HTMLParser()
    tree = etree.parse(StringIO.StringIO(content), parser)
    body = tree.xpath('//body/*')
    content = tostring(body[0])

    fontsize_regex = re.compile('font-size: .*;')
    content = re.sub(fontsize_regex, '', content)

    color_regex = re.compile('color: .*;')
    content = re.sub(color_regex, '', content)
    return content


def extract_from_doc(path, DEVNULL):
    '''Extract text from docs.

    We use antiword to pull the text out of MS Doc files.
    '''
    process = subprocess.Popen(['antiword', path, '-i', '1'], shell=False,
        stdout=subprocess.PIPE, stderr=DEVNULL)
    content, err = process.communicate()
    return content, err


def extract_from_html(path):
    '''Extract from html.

    A simple wrapper to go get content, and send it along.
    '''
    try:
        content = open(path).read()
        content = get_clean_body_content(content)
    except:
        content = ''
        err = True
    return content, err


def extract_from_pdf(doc, path, DEVNULL, callback=None):
    ''' Extract text from pdfs.

    Here, we use pdftotext. If that fails, try to use tesseract under the
    assumption it's an image-based PDF. Once that is complete, we check for the
    letter e in our content. If it's not there, we try to fix the mojibake
    that ca9 sometimes creates.
    '''
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
    '''Extract text from plain text files.

    This function is really here just for consistency.
    '''
    try:
        content = open(path).read()
    except:
        err = True
    return content, err


def extract_from_wpd(doc, path, DEVNULL):
    '''Extract text from a Word Perfect file

    Yes, courts still use these, so we extract their text using wpd2html. Once
    that's done, we pull out the body of the HTML, and do some minor cleanup
    on it.
    '''
    process = subprocess.Popen(['wpd2html', path, '-'], shell=False,
        stdout=subprocess.PIPE, stderr=DEVNULL)
    content, err = process.communicate()

    content = get_clean_body_content(content)

    if 'not for publication' in content.lower():
        doc.documentType = "Unpublished"

    return doc, content, err


@task
def extract_doc_content(pk, callback=None):
    '''
    Given a document, we extract it, sniffing its extension, then store its
    contents in the database.  Finally, we asynchronously find citations in
    the document content and match them to other documents.

    TODO: this implementation cannot be distributed due to using local paths.
    '''
    logger.info("Extracting contents of document %s" % (pk,))

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

    doc.documentPlainText, blocked = anonymize(content)
    if blocked:
        doc.blocked = True
        doc.date_blocked = date.today()

    if err:
        print "****Error extracting text from %s: %s****" % (extension, doc)
        return 1

    try:
        doc.save()
    except Exception, e:
        print "****Error saving text to the db for: %s****" % doc
        print traceback.format_exc()
        return 3

    # Identify and link citations within the document content
    update_document_by_id.delay(doc.pk)

    logger.info("Successfully extracted contents of document %s" % (pk,))
    return 0


@task
def extract_by_ocr(path):
    '''Extract the contents of a PDF using OCR

    Convert the PDF to a tiff, then perform OCR on the tiff using Tesseract.
    Take the contents and the exit code and return them to the caller.
    '''
    print "Running OCR subtask on %s" % path
    content = ''
    success = False
    try:
        DEVNULL = open('/dev/null', 'w')
        tmp_file_prefix = os.path.join('/tmp', str(time.time()))
        image_magick_command = ['convert', '-depth', '4', '-density', '300',
                                '-background', 'white', '+matte', path,
                                '%s.tiff' % tmp_file_prefix]
        process = subprocess.Popen(image_magick_command, shell=False,
                                   stdout=DEVNULL, stderr=DEVNULL)
        _, err = process.communicate()
        if not err:
            print "ran imagemagick successfully."
            tesseract_command = ['tesseract', '%s.tiff' % tmp_file_prefix,
                                 tmp_file_prefix, '-l', 'eng']
            process = subprocess.Popen(tesseract_command, shell=False,
                                       stdout=DEVNULL, stderr=DEVNULL)
            _, err = process.communicate()
            if not err:
                print "ran tesseract successfully."
                content = open('%s.txt' % tmp_file_prefix).read()
                success = True

    finally:
        # Remove tmp_file and the text file
        for suffix in ['.tiff', '.txt']:
            try:
                os.remove(tmp_file_prefix + suffix)
            except OSError:
                pass

    return success, content

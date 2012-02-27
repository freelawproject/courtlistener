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
from lxml import etree
from lxml.etree import tostring

import os
import re
import StringIO
import subprocess
import time


@task
def extract_doc_content(pk):
    '''
    Given a document, we extract it, sniffing its mimetype, then store its 
    contents in the database. 
    
    TODO: this implementation cannot be distributed due to using local paths.
    '''
    logger = extract_doc_content.get_logger()
    logger.info("Extracting contents of document %s" % (pk,))

    doc = Document.objects.get(pk=pk)

    path = str(doc.local_path)
    path = os.path.join(settings.MEDIA_ROOT, path)

    DEVNULL = open('/dev/null', 'w')
    mimetype = path.split('.')[-1]
    if mimetype == 'pdf':
        # do the pdftotext work for PDFs
        process = subprocess.Popen(["pdftotext", "-layout", "-enc", "UTF-8",
            path, "-"], shell=False, stdout=subprocess.PIPE, stderr=DEVNULL)
        content, err = process.communicate()
        if content.strip() == '':
            # probably an image PDF. Send it to OCR
            result = subtask("scrapers.tasks.extract_by_ocr", args=(path,), kwargs={}).apply()
            success, content = result.get()
            if success:
                doc.extracted_by_ocr = True
            elif content == '' or not success:
                content = "Unable to extract document content."
        elif 'e' not in content:
            # It's a corrupt PDF from ca9. Fix it.
            content = fix_mojibake(unicode(content, 'utf-8', errors='ignore'))

        doc.documentPlainText, blocked = anonymize(content)
        if blocked:
            doc.blocked = True
            doc.date_blocked = date.today()
        if err:
            print "****Error extracting PDF text from: %s****" % (doc.citation.case_name)
            return 1
    elif mimetype == 'txt':
        # read the contents of text files.
        try:
            content = open(path).read()
            doc.documentPlainText, blocked = anonymize(content)
        except:
            print "****Error extracting plain text from: %s****" % (doc.citation.case_name)
            return 1
    elif mimetype == 'wpd':
        # It's a Word Perfect file. Use the wpd2html converter, clean up
        # the HTML and save the content to the HTML field.
        process = subprocess.Popen(['wpd2html', path, '-'], shell=False,
            stdout=subprocess.PIPE, stderr=DEVNULL)
        content, err = process.communicate()

        parser = etree.HTMLParser()
        tree = etree.parse(StringIO.StringIO(content), parser)
        body = tree.xpath('//body')
        content = tostring(body[0]).replace('<body>', '').replace('</body>', '')

        fontsizeReg = re.compile('font-size: .*;')
        content = re.sub(fontsizeReg, '', content)

        colorReg = re.compile('color: .*;')
        content = re.sub(colorReg, '', content)

        if 'not for publication' in content.lower():
            doc.documentType = "Unpublished"
        doc.documentHTML, blocked = anonymize(content)

        if err:
            print "****Error extracting WPD text from: " + doc.citation.case_name + "****"
            return 1
    elif mimetype == 'doc':
        # read the contents of MS Doc files
        process = subprocess.Popen(['antiword', path, '-i', '1'], shell=False,
            stdout=subprocess.PIPE, stderr=DEVNULL)
        content, err = process.communicate()
        doc.documentPlainText, blocked = anonymize(content)
        if err:
            print "****Error extracting DOC text from: " + doc.citation.case_name + "****"
            return 1
    else:
        print "*****Unknown mimetype: " + mimetype + ". Unable to extract content from: " + doc.citation.case_name + "****"
        return 2

    try:
        doc.save()
    except Exception, e:
        print "****Error saving text to the db for: " + doc.citation.case_name + "****"
        return 3

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
        image_magick_command = ['convert', '-depth', '4', '-density', '300', path,
                        tmp_file_prefix + '.tiff']
        process = subprocess.Popen(image_magick_command, shell=False,
                                   stdout=DEVNULL, stderr=DEVNULL)
        _, err = process.communicate()
        if not err:
            tesseract_command = ['tesseract', tmp_file_prefix + '.tiff',
                                 tmp_file_prefix, '-l', 'eng']
            process = subprocess.Popen(tesseract_command, shell=False,
                                       stdout=DEVNULL, stderr=DEVNULL)
            _, err = process.communicate()

            if not err:
                content = open(tmp_file_prefix + '.txt').read()
                success = True

    finally:
        # Remove tmp_file and the text file
        for suffix in ['.tiff', '.txt']:
            try:
                os.remove(tmp_file_prefix + suffix)
            except OSError:
                pass

    return success, content

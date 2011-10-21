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

from alert.alertSystem.models import Document
from alert.lib.string_utils import anonymize
from celery.decorators import task
from lxml import etree
from lxml.etree import tostring

import re
import StringIO
import subprocess


@task
def extract_doc_content(pk):
    '''
    Given a document, we extract it, sniffing its mimetype, then store its 
    contents in the database. 
    
    TODO: this implementation cannot be distributed due to using local paths.
    '''
    logger = extract_doc_content.get_logger()
    logger.info("Extracting contents of document %s" % (pk,))

    doc = Document.objects.get(pk = pk)

    path = str(doc.local_path)
    path = settings.MEDIA_ROOT + path

    DEVNULL = open('/dev/null', 'w')
    mimetype = path.split('.')[-1]
    if mimetype == 'pdf':
        # do the pdftotext work for PDFs
        process = subprocess.Popen(["pdftotext", "-layout", "-enc", "UTF-8",
            path, "-"], shell = False, stdout = subprocess.PIPE, stderr = DEVNULL)
        content, err = process.communicate()
        if content == '':
            # probably an image PDF. TODO: Add code here to create OCR task in 
            # celery.
            content = "Unable to extract document content."
        doc.documentPlainText = anonymize(content)
        if err:
            print "****Error extracting PDF text from: " + doc.citation.caseNameShort + "****"
            return 1
    elif mimetype == 'txt':
        # read the contents of text files.
        try:
            content = open(path).read()
            doc.documentPlainText = anonymize(content)
        except:
            print "****Error extracting plain text from: " + doc.citation.caseNameShort + "****"
            return 1
    elif mimetype == 'wpd':
        # It's a Word Perfect file. Use the wpd2html converter, clean up
        # the HTML and save the content to the HTML field.
        process = subprocess.Popen(['wpd2html', path, '-'], shell = False,
            stdout = subprocess.PIPE, stderr = DEVNULL)
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
        doc.documentHTML = anonymize(content)

        if err:
            print "****Error extracting WPD text from: " + doc.citation.caseNameShort + "****"
            return 1
    elif mimetype == 'doc':
        # read the contents of MS Doc files
        process = subprocess.Popen(['antiword', path, '-i', '1'], shell = False,
            stdout = subprocess.PIPE, stderr = DEVNULL)
        content, err = process.communicate()
        doc.documentPlainText = anonymize(content)
        if err:
            print "****Error extracting DOC text from: " + doc.citation.caseNameShort + "****"
            return 1
    else:
        print "*****Unknown mimetype: " + mimetype + ". Unable to extract content from: " + doc.citation.caseNameShort + "****"
        return 2

    try:
        doc.save()
    except Exception, e:
        print "****Error saving text to the db for: " + doc.citation.caseNameShort + "****"
        return 3

    logger.info("Successfully extracted contents of document %s" % (pk,))
    return 0

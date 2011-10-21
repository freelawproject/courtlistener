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
def extract_doc_contents(pk):
    '''
    Given a document, we extract it, sniffing its mimetype, then store its 
    contents in the database. 
    
    This implementation cannot be distributed due to using local paths.
    '''
    doc = Document.objects.get(pk = pk)

    path = str(doc.local_path)
    path = settings.MEDIA_ROOT + path

    mimetype = path.split('.')[-1]
    if mimetype == 'pdf':
        # do the pdftotext work for PDFs
        process = subprocess.Popen(["pdftotext", "-layout", "-enc", "UTF-8",
            path, "-"], shell = False, stdout = subprocess.PIPE,
            stderr = subprocess.STDOUT)
        content, err = process.communicate()
        if content == '':
            # probably an image PDF. TODO: Add code here to create OCR task in 
            # celery.
            content = "Unable to extract document content."
        doc.documentPlainText = anonymize(content)
        if err:
            print "****Error extracting PDF text from: " + doc.citation.caseNameShort + "****"
    elif mimetype == 'txt':
        # read the contents of text files.
        try:
            content = open(path).read()
            doc.documentPlainText = anonymize(content)
        except:
            print "****Error extracting plain text from: " + doc.citation.caseNameShort + "****"
    elif mimetype == 'wpd':
        # It's a Word Perfect file. Use the wpd2html converter, clean up
        # the HTML and save the content to the HTML field.
        process = subprocess.Popen(['wpd2html', path, '-'], shell = False,
            stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
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
    elif mimetype == 'doc':
        # read the contents of MS Doc files
        process = subprocess.Popen(['antiword', path, '-i', '1'], shell = False,
            stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
        content, err = process.communicate()
        doc.documentPlainText = anonymize(content)
        if err:
            print "****Error extracting DOC text from: " + doc.citation.caseNameShort + "****"
    else:
        print "*****Unknown mimetype: " + mimetype + ". Unable to extract content from: " + doc.citation.caseNameShort + "****"

    try:
        doc.save()
    except Exception, e:
        print "****Error saving text to the db for: " + doc.citation.caseNameShort + "****"

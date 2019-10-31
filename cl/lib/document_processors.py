import random
import subprocess
import traceback
from tempfile import NamedTemporaryFile

from PyPDF2 import PdfFileReader
from PyPDF2.utils import PdfReadError
from django.utils.encoding import force_text, DjangoUnicodeDecodeError, \
    smart_text
from django.utils.timezone import now
from lxml.etree import XMLSyntaxError
from lxml.html.clean import Cleaner

from cl.celery import app
from cl.citations.tasks import find_citations_for_opinion_by_pks
from cl.lib.mojibake import fix_mojibake
from cl.lib.string_utils import anonymize
from cl.search.models import Opinion


def get_page_count(path, extension):
    """Get the number of pages, if appropriate mimetype.

    :param path: A path to a binary (pdf, wpd, doc, txt, html, etc.)
    :param extension: The extension of the binary.
    :return: The number of pages if possible, else return None
    """
    if extension == 'pdf':
        try:
            reader = PdfFileReader(path)
            return int(reader.getNumPages())
        except (IOError, ValueError, TypeError, KeyError, AssertionError,
                PdfReadError):
            # IOError: File doesn't exist. My bad.
            # ValueError: Didn't get an int for the page count. Their bad.
            # TypeError: NumberObject has no attribute '__getitem__'. Ugh.
            # KeyError, AssertionError: assert xrefstream["/Type"] == "/XRef". WTF?
            # PdfReadError: Something else. I have no words.
            pass
    elif extension == 'wpd':
        # Best solution appears to be to dig into the binary format
        pass
    elif extension == 'doc':
        # Best solution appears to be to dig into the XML of the file
        # itself: http://stackoverflow.com/a/12972502/64911
        pass
    return None


def make_pdftotext_process(path):
    """Make a subprocess to hand to higher-level code."""
    return subprocess.Popen(
        ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
        shell=False,
        stdout=subprocess.PIPE,
        stderr=DEVNULL
    )


@app.task
def extract_by_ocr(path):
    """Extract the contents of a PDF using OCR."""
    fail_msg = (u"Unable to extract the content from this file. Please try "
                u"reading the original.")
    with NamedTemporaryFile(prefix='ocr_', suffix=".tiff") as tmp:
        out, err, returncode = rasterize_pdf(path, tmp.name)
        if returncode != 0:
            return False, fail_msg

        txt = convert_file_to_txt(tmp.name)
        txt = cleanup_ocr_text(txt)

    return True, txt


def extract_from_pdf(path, opinion, do_ocr=False):
    """ Extract text from pdfs.

    Here, we use pdftotext. If that fails, try to use tesseract under the
    assumption it's an image-based PDF. Once that is complete, we check for the
    letter e in our content. If it's not there, we try to fix the mojibake
    that ca9 sometimes creates.
    """
    process = make_pdftotext_process(path)
    content, err = process.communicate()
    if content.strip() == '' and do_ocr:
        success, content = extract_by_ocr(path)
        if success:
            opinion.extracted_by_ocr = True
        elif content == '' or not success:
            content = 'Unable to extract document content.'
    elif 'e' not in content:
        # It's a corrupt PDF from ca9. Fix it.
        content = fix_mojibake(unicode(content, 'utf-8', errors='ignore'))

    return content, err


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


def extract_from_doc(path):
    """Extract text from docs.

    We use antiword to pull the text out of MS Doc files.
    """
    process = subprocess.Popen(['antiword', path, '-i', '1'], shell=False,
                               stdout=subprocess.PIPE, stderr=DEVNULL)
    content, err = process.communicate()
    return content, err


def extract_from_docx(path):
    """Extract text from docx files

    We use docx2txt to pull out the text. Pretty simple.
    """
    process = subprocess.Popen(['docx2txt', path, '-'], shell=False,
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
        encodings = ['utf-8', 'ISO8859', 'cp1252']
        for encoding in encodings:
            try:
                content = force_text(content, encoding=encoding)
            except DjangoUnicodeDecodeError:
                continue
            else:
                return content, False

        # Fell through, therefore unable to decode the string.
        return '', True
    except:
        return '', True


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


def extract_from_wpd(path, opinion):
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

    return content, err


def convert_file_to_txt(path):
    tesseract_command = ['tesseract', path, 'stdout', '-l', 'eng']
    p = subprocess.Popen(
        tesseract_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return p.communicate()[0].decode('utf-8')


@app.task
def extract_doc_content(pk, do_ocr=False, citation_jitter=False):
    """
    Given an opinion PK, we extract it, sniffing its extension, then store its
    contents in the database.  Finally, we asynchronously find citations in
    the document content and match them to other documents.

    This implementation uses local paths.

    :param pk: The opinion primary key to work on
    :param do_ocr: Whether the PDF converting function should use OCR
    :param citation_jitter: Whether to apply jitter before running the citation
    parsing code. This can be useful do spread these tasks out when doing a
    larger scrape.
    """
    opinion = Opinion.objects.get(pk=pk)

    path = opinion.local_path.path

    extension = path.split('.')[-1]
    if extension == 'doc':
        content, err = extract_from_doc(path)
    elif extension == 'docx':
        content, err = extract_from_docx(path)
    elif extension == 'html':
        content, err = extract_from_html(path)
    elif extension == 'pdf':
        content, err = extract_from_pdf(path, opinion, do_ocr)
    elif extension == 'txt':
        content, err = extract_from_txt(path)
    elif extension == 'wpd':
        content, err = extract_from_wpd(path, opinion)
    else:
        print ('*****Unable to extract content due to unknown extension: %s '
               'on opinion: %s****' % (extension, opinion))
        return

    # Do page count, if possible
    opinion.page_count = get_page_count(path, extension)

    # Do blocked status
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
        return

    # Save item, and index Solr if needed.
    # noinspection PyBroadException
    try:
        if not citation_jitter:
            # No waiting around. Save to the database now, but don't bother
            # with the index yet because citations are being done imminently.
            opinion.cluster.save(index=False)
            opinion.save(index=False)
        else:
            # Save to the index now, citations come later, commit comes
            # according to schedule
            opinion.cluster.save(index=False)
            opinion.save(index=True)
    except Exception:
        print("****Error saving text to the db for: %s****\n%s" %
              (opinion, traceback.format_exc()))
        return

    # Identify and link citations within the document content
    find_citations_for_opinion_by_pks.apply_async(
        ([opinion.pk],),
        countdown=random.randint(0, 3600)
    )


def rasterize_pdf(path, destination):
    """Convert the PDF into a multipage Tiff file.

    This function uses ghostscript for processing and borrows heavily from:

        https://github.com/jbarlow83/OCRmyPDF/blob/636d1903b35fed6b07a01af53769fea81f388b82/ocrmypdf/ghostscript.py#L11

    """
    # gs docs, see: http://ghostscript.com/doc/7.07/Use.htm
    # gs devices, see: http://ghostscript.com/doc/current/Devices.htm
    #
    # Compression is a trade off. It takes twice as long to convert PDFs, but
    # they're about 1-2% the size of the uncompressed version. They take about
    # 30% of the RAM when Tesseract processes them. See:
    # https://github.com/tesseract-ocr/tesseract/issues/431#issuecomment-250549208
    gs = [
        'gs',
        '-dQUIET',  # Suppress printing routine info
        '-dSAFER',  # Lock down the filesystem to only files on command line
        '-dBATCH',  # Exit after finishing file. Don't wait for more commands.
        '-dNOPAUSE',  # Don't pause after each page
        '-sDEVICE=tiffgray',
        '-sCompression=lzw',
        '-r300x300',  # Set the resolution to 300 DPI.
        '-o', destination,
        path,
    ]
    p = subprocess.Popen(gs, close_fds=True, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, universal_newlines=True)
    stdout, stderr = p.communicate()
    return stdout, stderr, p.returncode


def cleanup_ocr_text(txt):
    """Do some basic cleanup to make OCR text better.

    Err on the side of safety. Don't make fixes that could cause other issues.

    :param txt: The txt output from the OCR engine.
    :return: Txt output, cleaned up.
    """
    simple_replacements = (
        (u'Fi|ed', u'Filed'),
        (u' Il ', u' II '),
    )
    for replacement in simple_replacements:
        txt = txt.replace(replacement[0], replacement[1])
    return txt

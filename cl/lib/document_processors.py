import subprocess
from tempfile import NamedTemporaryFile

from PyPDF2 import PdfFileReader
from PyPDF2.utils import PdfReadError

from cl.celery import app
from cl.lib.mojibake import fix_mojibake
from cl.scrapers.tasks import DEVNULL, rasterize_pdf, convert_file_to_txt, \
    cleanup_ocr_text


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

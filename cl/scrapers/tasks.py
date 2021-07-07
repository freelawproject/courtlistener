import base64
import logging
import random
import re
import subprocess
import traceback
from tempfile import NamedTemporaryFile
from typing import List, Optional, Tuple, Union

import requests
from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.encoding import (
    DjangoUnicodeDecodeError,
    force_str,
    smart_str,
)
from juriscraper.pacer import CaseQuery, PacerSession
from lxml.etree import XMLSyntaxError
from lxml.html.clean import Cleaner
from PyPDF2 import PdfFileReader
from PyPDF2.utils import PdfReadError

from cl.audio.models import Audio
from cl.celery_init import app
from cl.citations.tasks import find_citations_for_opinion_by_pks
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.celery_utils import throttle_task
from cl.lib.juriscraper_utils import get_scraper_object_by_name
from cl.lib.mojibake import fix_mojibake
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.lib.privacy_tools import anonymize, set_blocked_status
from cl.lib.recap_utils import needs_ocr
from cl.lib.string_utils import trunc
from cl.lib.utils import is_iter
from cl.recap.mergers import save_iquery_to_docket
from cl.scrapers.transformer_extractor_utils import convert_and_clean_audio
from cl.search.models import Docket, Opinion, RECAPDocument

DEVNULL = open("/dev/null", "w")

logger = logging.getLogger(__name__)

ExtractProcessResult = Tuple[str, Optional[str]]


def get_clean_body_content(content: bytes) -> bytes:
    """Parse out the body from an html string and clean it up"""
    cleaner = Cleaner(
        style=True, remove_tags=["a", "body", "font", "noscript", "img"]
    )
    try:
        return cleaner.clean_html(content)
    except XMLSyntaxError:
        return (
            b"Unable to extract the content from this file. Please try "
            b"reading the original."
        )


def extract_from_doc(path: str) -> ExtractProcessResult:
    """Extract text from docs.

    We use antiword to pull the text out of MS Doc files.
    """
    process = subprocess.Popen(
        ["antiword", path, "-i", "1"],
        shell=False,
        stdout=subprocess.PIPE,
        stderr=DEVNULL,
    )
    content, err = process.communicate()
    if err is not None:
        err = err.decode()
    return content.decode(), err


def extract_from_docx(path: str) -> ExtractProcessResult:
    """Extract text from docx files

    We use docx2txt to pull out the text. Pretty simple.
    """
    process = subprocess.Popen(
        ["docx2txt", path, "-"],
        shell=False,
        stdout=subprocess.PIPE,
        stderr=DEVNULL,
    )
    content, err = process.communicate()
    if err is not None:
        err = err.decode()
    return content.decode(), err


def extract_from_html(path: str) -> Tuple[str, bool]:
    """Extract from html.

    A simple wrapper to go get content, and send it along.
    """
    try:
        with open(path, "rb") as f:
            content = f.read()
        content = get_clean_body_content(content)
        encodings = ["utf-8", "ISO8859", "cp1252"]
        for encoding in encodings:
            try:
                content = force_str(content, encoding=encoding)
            except DjangoUnicodeDecodeError:
                continue
            else:
                return content, False

        # Fell through, therefore unable to decode the string.
        return "", True
    except:
        return "", True


def make_pdftotext_process(path: str) -> subprocess.Popen:
    """Make a subprocess to hand to higher-level code."""
    return subprocess.Popen(
        ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
        shell=False,
        stdout=subprocess.PIPE,
        stderr=DEVNULL,
    )


def pdf_has_images(path: str) -> bool:
    """Check raw PDF for embedded images.

    We need to check if a PDF contains any images.  If a PDF contains images it
    likely has content that needs to be scanned.

    :param path: Location of PDF to process.
    :return: Does the PDF contain images?
    :type: bool
    """
    with open(path, "rb") as pdf_file:
        pdf_bytes = pdf_file.read()
        return True if re.search(rb"/Image ?/", pdf_bytes) else False


def ocr_needed(path: str, content: str) -> bool:
    """Check if OCR is needed on a PDF

    Check if images are in PDF or content is empty.

    :param path: The path to the PDF
    :param content: The content extracted from the PDF.
    :return: Whether OCR should be run on the document.
    """
    if content.strip() == "" or pdf_has_images(path):
        return True
    return False


def extract_from_pdf(
    path: str,
    opinion: Opinion,
    ocr_available: bool = False,
) -> ExtractProcessResult:
    """Extract text from pdfs.

    Start with pdftotext. If we we enabled OCR - and the the content is empty
    or the PDF contains images, use tesseract. This pattern occurs because PDFs
    can be images, text-based and a mix of the two. We check for images to
    make sure we do OCR on mix-type PDFs.

    If a text-based PDF we fix corrupt PDFs from ca9.

    :param path: The path to the PDF
    :param opinion: The Opinion associated with the PDF
    :param ocr_available: Whether we should do OCR stuff
    :return Tuple of the content itself and any errors we received
    """
    process = make_pdftotext_process(path)
    content, err = process.communicate()
    content = content.decode()
    if err is not None:
        err = err.decode()

    if not ocr_available:
        if "e" not in content:
            # It's a corrupt PDF from ca9. Fix it.
            content = fix_mojibake(content)
    else:
        if ocr_needed(path, content):
            success, ocr_content = extract_by_ocr(path)
            if success:
                # Check content length and take the longer of the two
                if len(ocr_content) > len(content):
                    content = ocr_content
                    opinion.extracted_by_ocr = True
            elif content == "" or not success:
                content = "Unable to extract document content."

    return content, err


def extract_from_txt(path: str) -> Tuple[str, bool]:
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
        with open(path, "rb") as f:
            data = f.read()
        try:
            # Alas, cp1252 is probably still more popular than utf-8.
            content = smart_str(data, encoding="cp1252")
        except DjangoUnicodeDecodeError:
            content = smart_str(data, encoding="utf-8", errors="ignore")
    except:
        err = True
        content = ""
    return content, err


def extract_from_wpd(path: str, opinion: Opinion) -> ExtractProcessResult:
    """Extract text from a Word Perfect file

    Yes, courts still use these, so we extract their text using wpd2html. Once
    that's done, we pull out the body of the HTML, and do some minor cleanup
    on it.
    """
    process = subprocess.Popen(
        ["wpd2html", path], shell=False, stdout=subprocess.PIPE, stderr=DEVNULL
    )
    content, err = process.communicate()

    content = get_clean_body_content(content)
    content = content.decode()
    if err is not None:
        err = err.decode()

    if "not for publication" in content.lower():
        opinion.precedential_status = "Unpublished"

    return content, err


def convert_file_to_txt(path: str) -> str:
    tesseract_command = ["tesseract", path, "stdout", "-l", "eng"]
    p = subprocess.Popen(
        tesseract_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return p.communicate()[0].decode()


def get_page_count(path: str, extension: str) -> Optional[int]:
    """Get the number of pages, if appropriate mimetype.

    :param path: A path to a binary (pdf, wpd, doc, txt, html, etc.)
    :param extension: The extension of the binary.
    :return: The number of pages if possible, else return None
    """
    if extension == "pdf":
        try:
            reader = PdfFileReader(path)
            return int(reader.getNumPages())
        except (
            IOError,
            ValueError,
            TypeError,
            KeyError,
            AssertionError,
            PdfReadError,
        ):
            # IOError: File doesn't exist. My bad.
            # ValueError: Didn't get an int for the page count. Their bad.
            # TypeError: NumberObject has no attribute '__getitem__'. Ugh.
            # KeyError, AssertionError: assert xrefstream["/Type"] == "/XRef". WTF?
            # PdfReadError: Something else. I have no words.
            pass
    elif extension == "wpd":
        # Best solution appears to be to dig into the binary format
        pass
    elif extension == "doc":
        # Best solution appears to be to dig into the XML of the file
        # itself: http://stackoverflow.com/a/12972502/64911
        pass
    return None


def update_document_from_text(opinion: Opinion) -> None:
    """Extract additional metadata from document text

    Use functions from Juriscraper to pull metadata out of opinion
    text. Currently only implemented in Tax, but functional in all
    scrapers via AbstractSite object.

    Note that this updates the values but does not save them. Saving is left to
    the calling function.

    :param opinion: Opinion object
    :return: None
    """
    court = opinion.cluster.docket.court.pk
    site = get_scraper_object_by_name(court)
    if site is None:
        return
    metadata_dict = site.extract_from_text(opinion.plain_text)
    for model_name, data in metadata_dict.items():
        ModelClass = apps.get_model(f"search.{model_name}")
        if model_name == "Docket":
            opinion.cluster.docket.__dict__.update(data)
        elif model_name == "OpinionCluster":
            opinion.cluster.__dict__.update(data)
        elif model_name == "Citation":
            data["cluster_id"] = opinion.cluster_id
            ModelClass.objects.get_or_create(**data)
        else:
            raise NotImplementedError(
                f"Object type of {model_name} not yet supported."
            )


@app.task
def extract_doc_content(
    pk: int,
    ocr_available: bool = False,
    citation_jitter: bool = False,
) -> None:
    """
    Given an opinion PK, we extract it, sniffing its extension, then store its
    contents in the database.  Finally, we asynchronously find citations in
    the document content and match them to other documents.

    This implementation uses local paths.

    :param pk: The opinion primary key to work on
    :param ocr_available: Whether the PDF converting function should use OCR
    :param citation_jitter: Whether to apply jitter before running the citation
    parsing code. This can be useful do spread these tasks out when doing a
    larger scrape.
    """
    opinion = Opinion.objects.get(pk=pk)
    extension = opinion.local_path.name.split(".")[-1]

    with NamedTemporaryFile(
        prefix="extract_file_",
        suffix=f".{extension}",
        buffering=0,  # Make sure it's on disk when we try to use it
    ) as tmp:
        # Get file contents from S3 and put them in a temp file.
        tmp.write(opinion.local_path.read())

        if extension == "doc":
            content, err = extract_from_doc(tmp.name)
        elif extension == "docx":
            content, err = extract_from_docx(tmp.name)
        elif extension == "html":
            content, err = extract_from_html(tmp.name)
        elif extension == "pdf":
            content, err = extract_from_pdf(tmp.name, opinion, ocr_available)
        elif extension == "txt":
            content, err = extract_from_txt(tmp.name)
        elif extension == "wpd":
            content, err = extract_from_wpd(tmp.name, opinion)
        else:
            print(
                "*****Unable to extract content due to unknown extension: %s "
                "on opinion: %s****" % (extension, opinion)
            )
            return

        # Do page count, if possible
        opinion.page_count = get_page_count(tmp.name, extension)

    assert isinstance(
        content, str
    ), f"content must be of type str, not {type(content)}"

    set_blocked_status(opinion, content, extension)
    update_document_from_text(opinion)

    if err:
        print(err)
        print(f"****Error extracting text from {extension}: {opinion}****")
        return

    # Save item, and index Solr if needed.
    # noinspection PyBroadException
    try:
        opinion.cluster.docket.save()
        opinion.cluster.save(index=False)
        if not citation_jitter:
            # No waiting around. Save to the database now, but don't bother
            # with the index yet because citations are being done imminently.
            opinion.save(index=False)
        else:
            # Save to the index now, citations come later, commit comes
            # according to schedule
            opinion.save(index=True)
    except Exception:
        print(
            "****Error saving text to the db for: %s****\n%s"
            % (opinion, traceback.format_exc())
        )
        return

    # Identify and link citations within the document content
    find_citations_for_opinion_by_pks.apply_async(
        ([opinion.pk],), countdown=random.randint(0, 3600)
    )


@app.task
def extract_recap_pdf(
    pks: Union[int, List[int]],
    skip_ocr: bool = False,
    check_if_needed: bool = True,
) -> List[int]:
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

        with NamedTemporaryFile(
            prefix="extract_file_",
            suffix=".pdf",
            buffering=0,  # Make sure it's on disk when we try to use it
        ) as tmp:
            tmp.write(rd.filepath_local.read())
            process = make_pdftotext_process(tmp.name)
            content, err = process.communicate()
            content = content.decode()

            if needs_ocr(content):
                if not skip_ocr:
                    # probably an image PDF. Send it to OCR.
                    success, content = extract_by_ocr(tmp.name)
                    if success:
                        rd.ocr_status = RECAPDocument.OCR_COMPLETE
                    elif content == "" or not success:
                        content = "Unable to extract document content."
                        rd.ocr_status = RECAPDocument.OCR_FAILED
                else:
                    content = ""
                    rd.ocr_status = RECAPDocument.OCR_NEEDED
            else:
                rd.ocr_status = RECAPDocument.OCR_UNNECESSARY

        rd.plain_text, _ = anonymize(content)
        # Do not do indexing here. Creates race condition in celery.
        rd.save(index=False, do_extraction=False)
        processed.append(pk)

    return processed


def rasterize_pdf(path: str, destination: str) -> Tuple[str, str, int]:
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
        "gs",
        "-dQUIET",  # Suppress printing routine info
        "-dSAFER",  # Lock down the filesystem to only files on command line
        "-dBATCH",  # Exit after finishing file. Don't wait for more commands.
        "-dNOPAUSE",  # Don't pause after each page
        "-sDEVICE=tiffgray",
        "-sCompression=lzw",
        "-r300x300",  # Set the resolution to 300 DPI.
        "-o",
        destination,
        path,
    ]
    p = subprocess.Popen(
        gs,
        close_fds=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    stdout, stderr = p.communicate()
    return stdout, stderr, p.returncode


def cleanup_ocr_text(txt: str) -> str:
    """Do some basic cleanup to make OCR text better.

    Err on the side of safety. Don't make fixes that could cause other issues.

    :param txt: The txt output from the OCR engine.
    :return: Txt output, cleaned up.
    """
    simple_replacements = (
        ("Fi|ed", "Filed"),
        (" Il ", " II "),
    )
    for replacement in simple_replacements:
        txt = txt.replace(replacement[0], replacement[1])
    return txt


@app.task
def extract_by_ocr(path: str) -> (bool, str):
    """Extract the contents of a PDF using OCR."""
    fail_msg = (
        "Unable to extract the content from this file. Please try "
        "reading the original."
    )
    with NamedTemporaryFile(prefix="ocr_", suffix=".tiff", buffering=0) as tmp:
        out, err, returncode = rasterize_pdf(path, tmp.name)
        if returncode != 0:
            return False, fail_msg

        txt = convert_file_to_txt(tmp.name)
        txt = cleanup_ocr_text(txt)

    return True, txt


@app.task(bind=True, max_retries=1, countdown=2)
def process_audio_file(self, pk) -> None:
    """Given the key to an audio file, extract its content and add the related
    meta data to the database.

    :param self: A Celery task object
    :param pk: Audio file pk
    :return: None
    """
    af = Audio.objects.get(pk=pk)
    bte_audio_response = convert_and_clean_audio(af)
    bte_audio_response.raise_for_status()
    audio_obj = bte_audio_response.json()
    cf = ContentFile(base64.b64decode(audio_obj["audio_b64"]))
    file_name = f"{trunc(best_case_name(af).lower(), 72)}_cl.mp3"
    af.file_with_date = af.docket.date_argued
    af.local_path_mp3.save(file_name, cf, save=False)
    af.duration = audio_obj["duration"]
    af.processing_complete = True
    af.save()


@app.task(bind=True, max_retries=2, interval_start=5, interval_step=5)
@throttle_task("2/s", key="court_id")
def update_docket_info_iquery(self, d_pk: int, court_id: str) -> None:
    """Update the docket info from iquery

    :param self: The Celery task
    :param d_pk: The ID of the docket
    :param court_id: The court of the docket. Needed for throttling by court.
    :return: None
    """
    cookies = get_or_cache_pacer_cookies(
        "pacer_scraper",
        settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    s = PacerSession(
        cookies=cookies,
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    d = Docket.objects.get(pk=d_pk, court_id=court_id)
    report = CaseQuery(map_cl_to_pacer_id(d.court_id), s)
    try:
        report.query(d.pacer_case_id)
    except (requests.Timeout, requests.RequestException) as exc:
        logger.warning(
            "Timeout or unknown RequestException on iquery crawl. "
            "Trying again if retries not exceeded."
        )
        if self.request.retries == self.max_retries:
            return
        raise self.retry(exc=exc)
    if not report.data:
        return

    save_iquery_to_docket(
        self,
        report.data,
        d,
        tag_names=None,
        add_to_solr=True,
    )

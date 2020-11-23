# -*- coding: utf-8 -*-

import logging
import random
import subprocess
import traceback
from tempfile import NamedTemporaryFile

import requests
from PyPDF2 import PdfFileReader
from PyPDF2.utils import PdfReadError
from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.utils.timezone import now
from lxml.etree import XMLSyntaxError
from lxml.html.clean import Cleaner
from requests import Timeout

from cl.audio.models import Audio
from cl.celery_init import app
from cl.citations.tasks import find_citations_for_opinion_by_pks
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.juriscraper_utils import get_scraper_object_by_name
from cl.lib.mojibake import fix_mojibake
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.lib.recap_utils import needs_ocr
from cl.lib.string_utils import anonymize, trunc
from cl.lib.utils import is_iter
from cl.recap.mergers import (
    update_docket_metadata,
    add_bankruptcy_data_to_docket,
)
from cl.scrapers.models import ErrorLog
from cl.scrapers.transformer_extractor_utils import (
    convert_and_clean_audio,
)
from cl.search.models import Opinion, RECAPDocument, Docket
from cl.search.tasks import add_items_to_solr
from juriscraper.pacer import PacerSession, CaseQuery

logger = logging.getLogger(__name__)


def get_clean_body_content(content):
    """Parse out the body from an html string, clean it up, and send it along."""
    cleaner = Cleaner(
        style=True, remove_tags=["a", "body", "font", "noscript", "img"]
    )
    try:
        return cleaner.clean_html(content)
    except XMLSyntaxError:
        return (
            "Unable to extract the content from this file. Please try "
            "reading the original."
        )


def extract_from_doc(path):
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
    return content.decode(), err


def extract_from_docx(path):
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
    return content.decode(), err


def extract_from_html(path):
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
                content = force_text(content, encoding=encoding)
            except DjangoUnicodeDecodeError:
                continue
            else:
                return content, False

        # Fell through, therefore unable to decode the string.
        return "", True
    except:
        return "", True


def make_pdftotext_process(path):
    """Make a subprocess to hand to higher-level code."""
    return subprocess.Popen(
        ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
        shell=False,
        stdout=subprocess.PIPE,
        stderr=DEVNULL,
    )


def extract_from_pdf(path, opinion, do_ocr=False):
    """Extract text from pdfs.

    Here, we use pdftotext. If that fails, try to use tesseract under the
    assumption it's an image-based PDF. Once that is complete, we check for the
    letter e in our content. If it's not there, we try to fix the mojibake
    that ca9 sometimes creates.
    """
    process = make_pdftotext_process(path)
    content, err = process.communicate()
    content = content.decode()
    if content.strip() == "" and do_ocr:
        success, content = extract_by_ocr(path)
        if success:
            opinion.extracted_by_ocr = True
        elif content == "" or not success:
            content = "Unable to extract document content."
    elif "e" not in content:
        # It's a corrupt PDF from ca9. Fix it.
        content = fix_mojibake(content)
    return content, err


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
        with open(path, "rb") as f:
            data = f.read()
        try:
            # Alas, cp1252 is probably still more popular than utf-8.
            content = smart_text(data, encoding="cp1252")
        except DjangoUnicodeDecodeError:
            content = smart_text(data, encoding="utf-8", errors="ignore")
    except:
        err = True
        content = ""
    return content, err


def extract_from_wpd(path, opinion):
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

    if "not for publication" in content.lower():
        opinion.precedential_status = "Unpublished"

    return content, err


def convert_file_to_txt(path):
    tesseract_command = ["tesseract", path, "stdout", "-l", "eng"]
    p = subprocess.Popen(
        tesseract_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return p.communicate()[0].decode()


def get_page_count(path, extension):
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


def update_document_from_text(opinion):
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
        ModelClass = apps.get_model("search.%s" % model_name)
        if model_name == "Docket":
            opinion.cluster.docket.__dict__.update(data)
        elif model_name == "OpinionCluster":
            opinion.cluster.__dict__.update(data)
        elif model_name == "Citation":
            data["cluster_id"] = opinion.cluster_id
            ModelClass.objects.get_or_create(**data)
        else:
            raise NotImplementedError(
                "Object type of %s not yet supported." % model_name
            )


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

    extension = path.split(".")[-1]
    if extension == "doc":
        content, err = extract_from_doc(path)
    elif extension == "docx":
        content, err = extract_from_docx(path)
    elif extension == "html":
        content, err = extract_from_html(path)
    elif extension == "pdf":
        content, err = extract_from_pdf(path, opinion, do_ocr)
    elif extension == "txt":
        content, err = extract_from_txt(path)
    elif extension == "wpd":
        content, err = extract_from_wpd(path, opinion)
    else:
        print(
            "*****Unable to extract content due to unknown extension: %s "
            "on opinion: %s****" % (extension, opinion)
        )
        return

    assert isinstance(
        content, str
    ), "content must be of type str, not %s" % type(content)

    # Do page count, if possible
    opinion.page_count = get_page_count(path, extension)

    # Do blocked status
    if extension in ["html", "wpd"]:
        opinion.html, blocked = anonymize(content)
    else:
        opinion.plain_text, blocked = anonymize(content)
    if blocked:
        opinion.cluster.blocked = True
        opinion.cluster.date_blocked = now()

    update_document_from_text(opinion)

    if err:
        print(err)
        print(
            "****Error extracting text from %s: %s****" % (extension, opinion)
        )
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
        content = content.decode()

        if needs_ocr(content):
            if not skip_ocr:
                # probably an image PDF. Send it to OCR.
                success, content = extract_by_ocr(path)
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

@app.task

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


def cleanup_ocr_text(txt):
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
    with NamedTemporaryFile(prefix="ocr_", suffix=".tiff") as tmp:
        out, err, returncode = rasterize_pdf(path, tmp.name)
        if returncode != 0:
            return False, fail_msg

        txt = convert_file_to_txt(tmp.name)
        txt = cleanup_ocr_text(txt)

    return True, txt


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
    audio_file.tag.album = "{court}, {year}".format(
        court=court.full_name, year=audio_obj.docket.date_argued.year
    )
    audio_file.tag.artist = court.full_name
    audio_file.tag.artist_url = court.url
    audio_file.tag.audio_source_url = audio_obj.download_url
    audio_file.tag.comments.set(
        "Argued: {date_argued}. Docket number: {docket_number}".format(
            date_argued=audio_obj.docket.date_argued.strftime("%Y-%m-%d"),
            docket_number=audio_obj.docket.docket_number,
        )
    )
    audio_file.tag.genre = "Speech"
    audio_file.tag.publisher = "Free Law Project"
    audio_file.tag.publisher_url = "https://free.law"
    audio_file.tag.recording_date = audio_obj.docket.date_argued.strftime(
        "%Y-%m-%d"
    )

    # Add images to the mp3. If it has a seal, use that for the Front Cover
    # and use the FLP logo for the Publisher Logo. If it lacks a seal, use the
    # Publisher logo for both the front cover and the Publisher logo.
    try:
        has_seal = seals_data[court.pk]["has_seal"]
    except AttributeError:
        # Unknown court in Seal Rookery.
        has_seal = False
    except KeyError:
        # Unknown court altogether (perhaps a test?)
        has_seal = False

    flp_image_frames = [
        3,  # "Front Cover". Complete list at eyed3/id3/frames.py
        14,  # "Publisher logo".
    ]
    if has_seal:
        with open(
            os.path.join(seals_root, "512", "%s.png" % court.pk), "rb"
        ) as f:
            audio_file.tag.images.set(
                3, f.read(), "image/png", "Seal for %s" % court.short_name
            )
        flp_image_frames.remove(3)

    for frame in flp_image_frames:
        with open(
            os.path.join(
                settings.INSTALL_ROOT,
                "cl",
                "audio",
                "static",
                "png",
                "producer-300x300.png",
            ),
            "rb",
        ) as f:
            audio_file.tag.images.set(
                frame,
                f.read(),
                "image/png",
                "Created for the public domain by Free Law Project",
            )

    audio_file.tag.save()


@app.task
def process_audio_file(pk):
    """Given the key to an audio file, extract its content and add the related
    meta data to the database.
    """
    af = Audio.objects.get(pk=pk)
    try:
        response = convert_and_clean_audio(af).json()
        cf = ContentFile(response["content"])
        file_name = trunc(best_case_name(af).lower(), 72) + "_cl.mp3"
        af.file_with_date = af.docket.date_argued
        af.local_path_mp3.save(file_name, cf, save=False)
        af.duration = response["duration"]

    except Timeout:
        ErrorLog.objects.create(
            log_level="CRITICAL",
            court=af.docket.court,
            message="Timeout occurred in docker container for %s" % (af.pk),
        )
    except:
        msg = (
            "Unable to save mp3 to audio_file in scraper.tasks."
            "process_audio_file for item: %s\n"
            "Traceback:\n"
            "%s" % (af.pk, traceback.format_exc())
        )
        print(msg)
        ErrorLog.objects.create(
            log_level="CRITICAL", court=af.docket.court, message=msg
        )
    af.processing_complete = True
    af.save()


@app.task(bind=True, max_retries=2, interval_start=5, interval_step=5)
def update_docket_info_iquery(self, d_pk):
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
    d = Docket.objects.get(pk=d_pk)
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

    d = update_docket_metadata(d, report.data)
    try:
        d.save()
        add_bankruptcy_data_to_docket(d, report.data)
    except IntegrityError as exc:
        msg = "Integrity error while saving iquery response."
        if self.request.retries == self.max_retries:
            logger.warn(msg)
            return
        logger.info(msg=" Retrying.")
        raise self.retry(exc=exc)
    add_items_to_solr([d.pk], "search.Docket")

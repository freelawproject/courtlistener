import re

from django.conf import settings

BASE_DOWNLOAD_URL = "https://www.archive.org/download"


def get_bucket_name(court, pacer_case_id):
    bucketlist = ["gov", "uscourts", court, str(pacer_case_id)]
    if settings.DEBUG is True:
        bucketlist.insert(0, "dev")
    return ".".join(bucketlist)


def get_docketxml_url(court, pacer_case_id):
    return "{}/{}/{}".format(
        BASE_DOWNLOAD_URL,
        get_bucket_name(court, pacer_case_id),
        get_docket_filename(court, pacer_case_id, "xml"),
    )


def get_docketxml_url_from_path(path):
    """Similar to above, but uses path of single file to figure out the rest.

    E.g. this:
        /home/mlissner/Programming/intellij/courtlistener/cl/assets/media/recap/gov.uscourts.wyd.16083.docket.xml
    Becomes this:
        https://www.archive.org/download/gov.uscourts.wyd.16083/gov.uscourts.wyd.16083.docket.xml
        https://www.archive.org/download/gov/gov.uscourts.akd.23118.docket.xml
    """
    filename = path.rsplit("/", 1)[-1]
    bucket = ".".join(filename.split(".")[0:4])
    return f"{BASE_DOWNLOAD_URL}/{bucket}/{filename}"


def get_ia_document_url_from_path(path, document_number, attachment_number):
    """Make an IA URL based on the download path of an item."""
    filename = path.rsplit("/", 1)[-1]
    bucket = ".".join(filename.split(".")[0:4])
    return f"{BASE_DOWNLOAD_URL}/{bucket}/{bucket}.{document_number}.{attachment_number}.pdf"


def get_local_document_url_from_path(path, document_number, attachment_number):
    """Make a path to a local copy of a PDF."""
    filename = path.rsplit("/", 1)[-1]
    bucket = ".".join(filename.split(".")[0:4])
    return f"{bucket}.{document_number}.{attachment_number}.pdf"


def get_pdf_url(court, pacer_case_id, filename):
    return f"{BASE_DOWNLOAD_URL}/{get_bucket_name(court, pacer_case_id)}/{filename}"


def get_docket_filename(court, pacer_case_id, ext):
    return ".".join(
        [
            "gov",
            "uscourts",
            str(court),
            str(pacer_case_id),
            f"docket.{ext}",
        ]
    )


def get_document_filename(
    court, pacer_case_id, document_number, attachment_number
):
    return ".".join(
        [
            "gov",
            "uscourts",
            str(court),
            str(pacer_case_id),
            str(document_number),
            str(attachment_number or 0),
            "pdf",
        ]
    )


PAGINATION_OF_RE = re.compile(r"\bPage\s+\d+\s+of\s+\d+\b", re.I)
PAGINATION_PG_OF_RE = re.compile(r"\bPg\s+\d+\s+of\s+\d+\b", re.I)
PAGINATION_COLON_RE = re.compile(r"\bPage:\s*\d+\b", re.I)


def is_page_line(line: str) -> bool:
    """Detect if a line is a page-number marker.

    :param line: A single textual line extracted from a PDF.
    :return: True if the line matches "Page X of Y" or "Page: X"; False otherwise.
    """
    return bool(
        PAGINATION_OF_RE.search(line)
        or PAGINATION_COLON_RE.search(line)
        or PAGINATION_PG_OF_RE.search(line)
    )


def is_doc_common_header(line: str) -> bool:
    """Identify common header/footer lines that should be ignored.

    :param line: A line extracted from a PDF.
    :return: True if the line is empty, begins with common header starters, or
    matches pagination, filing, date/time, or "Received" patterns. False otherwise.
    """
    bad_starters = (
        "Appellate",
        "Appeal",
        "Case",
        "Desc",
        "Document",
        "Entered",
        "Main Document",
        "Page",
        "Received:",
        "USCA",
    )
    doc_filed_re = re.compile(r"\b(Filed|Date Filed)\b")
    date_re = re.compile(r"\b\d{2}/\d{2}/\d{2}\b")
    time_re = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")
    received_re = re.compile(r"\bReceived:\s*\d{2}/\d{2}/\d{2}(?:\d{2})?\b")

    if not line:
        return True
    if line.startswith(bad_starters):
        return True
    if (
        PAGINATION_OF_RE.search(line)
        or PAGINATION_COLON_RE.search(line)
        or doc_filed_re.search(line)
        or date_re.search(line)
        or time_re.search(line)
        or received_re.search(line)
    ):
        return True
    return False


def needs_ocr(content):
    """Determines if OCR is needed for a PACER PDF.

    Every document in PACER (pretty much) has the case number written on the
    top of every page. This is a great practice, but it means that to test if
    OCR is needed, we need to remove this text and see if anything is left. The
    line usually looks something like:

        Case 2:06-cv-00376-SRW Document 1-2 Filed 04/25/2006 Page 1 of 1
        Appeal: 15-1504 Doc: 6 Filed: 05/12/2015 Pg: 1 of 4
        Appellate Case: 14-3253 Page: 1 Date Filed: 01/14/2015 Entry ID: 4234486
        USCA Case #16-1062 Document #1600692 Filed: 02/24/2016 Page 1 of 3
        USCA11 Case: 21-12355 Date Filed: 07/13/202 Page: 1 of 2

    Some bankruptcy cases also have two-line headers due to the document
    description being in the header. That means the second line often looks
    like:

        Page 1 of 90
        Main Document Page 1 of 16
        Document     Page 1 of 12
        Invoices Page 1 of 57
        A - RLF Invoices Page 1 of 83
        Final Distribution Report Page 1 of 5

    This function first checks for valid content lines between pages. If there
    is no content, or it’s too short, we can say that at least that page
    requires OCR, so this method returns True.

    For example, with a line_count_threshold of 3, the following document will
    return True.

    Case: 08-9007   Document: 00115928542   Page: 1   Date Filed: 07/30/2009   Entry ID: 5364336
    Line 1
    Case: 08-9007   Document: 00115928542   Page: 2   Date Filed: 07/30/2009   Entry ID: 5364336
    Line 1


    As a fallback it removes these common headers so that if no text remains,
    we can be sure that the PDF needs OCR.

    :param content: The content of a PDF.
    :return: boolean indicating if OCR is needed.
    """
    # Minimum number of valid lines between common headers to consider that the page
    # does not need OCR.
    lines = (ln.strip() for ln in content.splitlines())
    in_page = False
    other_content_count = 0
    saw_any_page = False
    for line in lines:
        if is_page_line(line):
            if in_page:
                if other_content_count < settings.LINE_THRESHOLD_OCR_PER_PAGE:
                    return True
            in_page = True
            saw_any_page = True
            other_content_count = 0
            continue

        if not in_page:
            continue

        # inside a page, count only non-common header lines
        if not is_doc_common_header(line):
            other_content_count += 1

    # end of document, close the trailing page
    if in_page:
        if other_content_count < settings.LINE_THRESHOLD_OCR_PER_PAGE:
            return True

    # If no pages were found, fall back to the regular behavior of checking whether
    # any content remains after removing common headers.
    if not saw_any_page:
        for line in content.splitlines():
            if not is_doc_common_header(line.strip()):
                return False
        return True

    return False

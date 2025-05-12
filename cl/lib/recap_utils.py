import re

from django.conf import settings

BASE_DOWNLOAD_URL = "https://www.archive.org/download"


def get_bucket_name(court, pacer_case_id):
    bucketlist = ["gov", "uscourts", court, str(pacer_case_id)]
    if settings.DEBUG is True:
        bucketlist.insert(0, "dev")
    return ".".join(bucketlist)


def get_docketxml_url(court, pacer_case_id):
    return "%s/%s/%s" % (
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

    This function removes these lines so that if no text remains, we can be sure
    that the PDF needs OCR.

    :param content: The content of a PDF.
    :return: boolean indicating if OCR is needed.
    """
    bad_starters = (
        "Appellate",
        "Appeal",
        "Case",
        "Page",
        "USCA",
    )
    pagination_re = re.compile(r"Page\s+\d+\s+of\s+\d+")
    for line in content.splitlines():
        line = line.strip()
        if line.startswith(bad_starters):
            continue
        elif pagination_re.search(line):
            continue
        elif line:
            # We found a line with good content. No OCR needed.
            return False

    # We arrive here if no line was found containing good content.
    return True

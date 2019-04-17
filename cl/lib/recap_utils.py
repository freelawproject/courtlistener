from django.conf import settings

BASE_DOWNLOAD_URL = "https://www.archive.org/download"


def get_bucket_name(court, pacer_case_id):
    bucketlist = ["gov", "uscourts", court, unicode(pacer_case_id)]
    if settings.DEBUG is True:
        bucketlist.insert(0, 'dev')
    return ".".join(bucketlist)


def get_docketxml_url(court, pacer_case_id):
    return "%s/%s/%s" % (
        BASE_DOWNLOAD_URL,
        get_bucket_name(court, pacer_case_id),
        get_docket_filename(court, pacer_case_id, 'xml'),
    )


def get_docketxml_url_from_path(path):
    """Similar to above, but uses path of single file to figure out the rest.

    E.g. this:
        /home/mlissner/Programming/intellij/courtlistener/cl/assets/media/recap/gov.uscourts.wyd.16083.docket.xml
    Becomes this:
        https://www.archive.org/download/gov.uscourts.wyd.16083/gov.uscourts.wyd.16083.docket.xml
        https://www.archive.org/download/gov/gov.uscourts.akd.23118.docket.xml
    """
    filename = path.rsplit('/', 1)[-1]
    bucket = '.'.join(filename.split('.')[0:4])
    return "%s/%s/%s" % (
        BASE_DOWNLOAD_URL,
        bucket,
        filename,
    )


def get_ia_document_url_from_path(path, document_number, attachment_number):
    """Make an IA URL based on the download path of an item."""
    filename = path.rsplit('/', 1)[-1]
    bucket = '.'.join(filename.split('.')[0:4])
    return "{url}/{bucket}/{bucket}.{doc_num}.{att_num}.pdf".format(
        url=BASE_DOWNLOAD_URL,
        bucket=bucket,
        doc_num=document_number,
        att_num=attachment_number,
    )


def get_local_document_url_from_path(path, document_number, attachment_number):
    """Make a path to a local copy of a PDF."""
    filename = path.rsplit('/', 1)[-1]
    bucket = '.'.join(filename.split('.')[0:4])
    return "{bucket}.{doc_num}.{att_num}.pdf".format(
        bucket=bucket,
        doc_num=document_number,
        att_num=attachment_number,
    )


def get_pdf_url(court, pacer_case_id, filename):
    return "%s/%s/%s" % (
        BASE_DOWNLOAD_URL,
        get_bucket_name(court, pacer_case_id),
        filename,
    )


def get_docket_filename(court, pacer_case_id, ext):
    return ".".join(["gov", "uscourts", unicode(court), unicode(pacer_case_id),
                     "docket.%s" % ext])


def get_document_filename(court, pacer_case_id, document_number,
                          attachment_number):
    return ".".join(["gov", "uscourts", unicode(court), unicode(pacer_case_id),
                     unicode(document_number), unicode(attachment_number or 0),
                     "pdf"])


def needs_ocr(content):
    """Determines if OCR is needed for a PACER PDF.

    Every document in PACER (pretty much) has the case number written on the
    top of every page. This is a great practice, but it means that to test if
    OCR is needed, we need to remove this text and see if anything is left. The
    line usually looks something like:

    Case 2:06-cv-00376-SRW Document 1-2 Filed 04/25/2006 Page 1 of 1

    This function removes these lines so that if no text remains, we can be sure
    that the PDF needs OCR.

    :param content: The content of a PDF.
    :return: boolean indicating if OCR is needed.
    """
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('Case'):
            continue
        elif line:
            # We found a line with good content. No OCR needed.
            return False

    # We arrive here if no line was found containing good content.
    return True

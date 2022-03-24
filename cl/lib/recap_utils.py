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
    return "{url}/{bucket}/{bucket}.{doc_num}.{att_num}.pdf".format(
        url=BASE_DOWNLOAD_URL,
        bucket=bucket,
        doc_num=document_number,
        att_num=attachment_number,
    )


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

import os

import requests
from django.conf import settings


def document_extract(path=None, file_content=None, do_ocr=False):
    """Extract document content.

    :param path:
    :param file_content:
    :param do_ocr:
    :return:
    """
    service = "%s/%s" % (settings.BTE_URL, "extract_doc_content")
    if path is not None:
        with open(path, "rb") as file:
            file_content = file.read()
    elif file_content is None:
        return {"err": "File not supplied"}

    if path is not None:
        file_name = os.path.basename(path)
    else:
        file_name = os.path.basename(file_content.name)
    return requests.post(
        url=service,
        files={"file": (file_name, file_content)},
        params={"do_ocr": do_ocr},
        timeout=60 * 60,
    ).json()


def convert_audio(path=None, file_content=None):
    """Convert audio file to MP3

    :param path:
    :return:
    """
    service = "%s/%s" % (settings.BTE_URL, "convert_audio_file")
    if path is not None:
        with open(path, "rb") as file:
            file_content = file.read()
    elif file_content is None:
        return {"err": "File not supplied"}

    response = requests.post(
        url=service,
        files={"file": ("some.wav", file_content)},
        timeout=60 * 60,
    ).json()
    return response


def generate_thumbnail(path=None, file_content=None):
    """Generate a thumbnail of page 1 of a PDF

    :param path:
    :return:
    """
    service = "%s/%s" % (settings.BTE_URL, "make_png_thumbnail")
    if path is not None:
        with open(path, "rb") as file:
            file_content = file.read()
    elif file_content is None:
        return {"err": "File not supplied"}

    return requests.post(
        url=service,
        files={"file": ("some.pdf", file_content)},
        timeout=60,
    ).json()


def get_page_count(path=None, file_content=None):
    """Get page count from document

    Sends file to binary-transformers-and-extractors and returns a json
    object containing the pg count

    :param path: path of the document
    :param pdf_bytes:
    :return:  {"pg_count: "", "err": ""}
    """
    service = "%s/%s" % (settings.BTE_URL, "get_page_count")
    if path is not None:
        with open(path, "rb") as file:
            file_content = file.read()
    elif file_content is None:
        return {"err": "File not supplied"}

    return requests.post(
        url=service,
        files={"file": ("some.pdf", file_content)},
        timeout=60,
    ).json()


def extract_jw_financial_document(
    url=None, file_content=None, judicial_watch=False
):
    """Extract financial data from financial disclosures.

    :return: Financial data
    :type: dict
    """
    endpoint = "extract"
    if judicial_watch:
        endpoint = "jw_extract"

    service = "%s/%s/%s" % (
        settings.BTE_URL,
        "financial_disclosure",
        endpoint,
    )
    if file_content is not None:
        files = {"file": ("some.pdf", file_content)}
    else:
        files = None
    response = requests.post(
        url=service,
        files=files,
        params={"url": url},
    )
    return response


def make_pdf_from_single_image(aws_path=None, file_content=None):
    """Send aws path to BTE to generate pdf from single tiff

    :return: pdf file
    """
    service = "%s/%s/%s" % (
        settings.BTE_URL,
        "financial_disclosure",
        "single_image",
    )
    response = requests.post(
        url=service,
        params={"aws_path": aws_path},
    )
    return response


def make_pdf_from_multiple_images(aws_path=None, file_content=None):
    """Pass aws path to BTE to generate PDF from many tiffs

    :return: pdf file
    """
    service = "%s/%s/%s" % (
        settings.BTE_URL,
        "financial_disclosure",
        "multi_image",
    )
    response = requests.post(
        url=service,
        params={"aws_path": aws_path},
    )
    return response

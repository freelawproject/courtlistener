import json
import os
from tempfile import NamedTemporaryFile

import requests
from django.conf import settings
from django.core import serializers


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


def serialize_audio_object(af):
    """

    :param af: Audio File Object
    :return: Convert audio w/ metadata
    """
    af_dict = json.loads(serializers.serialize("json", [af]))[0]["fields"]
    docket_dict = json.loads(serializers.serialize("json", [af.docket]))[0][
        "fields"
    ]
    court_dict = json.loads(serializers.serialize("json", [af.docket.court]))[
        0
    ]["fields"]
    af_dict["docket"] = docket_dict
    af_dict["docket"]["court"] = court_dict
    with NamedTemporaryFile(suffix=".json") as tmp:
        with open(tmp.name, "w") as json_data:
            json.dump(af_dict, json_data)
        with open(tmp.name, "rb") as file:
            af = file.read()
    return af


def convert_and_clean_audio(af):
    """Convert audio file to MP3 and add metadata

    :param path:
    :return:
    """
    service = "%s/%s/%s" % (settings.BTE_URL, "convert", "audio")
    audio_json = serialize_audio_object(af)
    with open(af.local_path_original_file.path, "rb") as wma_file:
        wav = wma_file.read()

    files = {
        "file": ("the_audio.wav", wav),
        "af": ("the_json.json", audio_json),
    }
    return requests.post(
        url=service,
        files=files,
        timeout=60 * 60,
    )


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

import json
import os
from tempfile import NamedTemporaryFile

import requests
from django.conf import settings
from django.core import serializers


def document_extract(path=None, file_content=None, do_ocr=False):
    """Extract document content for different file types.

    :param path: File path location
    :param file_content: Byte representation of the document
    :param do_ocr: Should we OCR the document
    :return: File content
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
    """Convert serialize aduio object into json for processing.

    :param af: Audio File object
    :return: Modified serailized audio file for processing in BTE
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


def convert_and_clean_audio(audio_obj):
    """Convert audio file to MP3 w/ metadata and image.

    :param audio_obj: Audio file object
    :return: Processed audio file
    :type: JSON object
    """
    with open(audio_obj.local_path_original_file.path, "rb") as audio_file:
        return requests.post(
            url="%s/%s/%s" % (settings.BTE_URL, "convert", "audio"),
            params={"audio_obj": serialize_audio_object(audio_obj)},
            files={
                "file": ("audio_file", audio_file.read()),
            },
            timeout=60 * 60,
        )


def extract_mime_type_from(file_path=None, bytes=None, mime=False):
    """Extract mime type from file or buffer/bytes.

    :param file_path: File location
    :param bytes: Files byte repr
    :return: Mime type
    """
    service = "%s/%s/%s" % (settings.BTE_URL, "utility", "mime_type")
    if file_path:
        with open(file_path, "rb") as file:
            f = file.read()
            file_obj = {"file": ("tmpfile", f)}
    else:
        file_obj = {"file": ("tmpfile", bytes)}
    response = requests.post(
        url=service,
        params={"mime": mime},
        files=file_obj,
        timeout=60,
    ).json()
    return response["mimetype"]


def generate_thumbnail(path=None, file_content=None):
    """Generate a thumbnail of page 1 of a PDF.

    :param path: PDF file location
    :param file_content: Byte repr of pdf
    :return: Thumbnail of PDF
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
    """Get page count from a document.

    Sends file to binary-transformers-and-extractors and returns a json
    object containing the pg count

    :param path: path of the document
    :param file_content: Byte representation of file
    :return: Page count of file
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

    :param url: AWS path to judicial watch document
    :param file_content: Byte representation of judical watch doc
    :param judicial_watch: Should we use judicial watch specific extration
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
    """Send aws_path to BTE to generate pdf from single tiff.

    :param aws_path: AWS path of image
    :param file_content: Byte representation of image
    :return: Converted image to PDF
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
    """Pass aws path to BTE to generate PDF from many tiffs.

    :param aws_path: AWS path of image
    :param file_content: Byte representation of image
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

import os

import requests
from django.conf import settings
from requests import Timeout


def document_extract(path, do_ocr=False):
    """Extract document content.

    :param path:
    :param do_ocr:
    :return:
    """
    service = "%s/%s" % (settings.BTE_URL, "extract_doc_content")
    with open(path, "rb") as file:
        f = file.read()
    try:
        return requests.post(
            url=service,
            files={"file": (os.path.basename(path), f)},
            params={"do_ocr": do_ocr},
            timeout=60 * 60,
        ).json()
    except Timeout:
        return {"err": Timeout}
    except:
        return {"err": "Unknown error occurred"}


def convert_audio(path):
    """Convert audio file to MP3

    :param path:
    :return:
    """
    service = "%s/%s" % (settings.BTE_URL, "convert_audio_file")
    with open(path, "rb") as file:
        f = file.read()
    try:
        response = requests.post(
            url=service,
            files={"file": (os.path.basename(path), f)},
            timeout=60 * 60,
        )
        return {"content": response.content, "err": response.headers["err"]}
    except Timeout:
        return {"err": Timeout}
    except:
        return {"err": "Unknown error occurred"}


def generate_thumbnail(path):
    """Generate a thumbnail of page 1 of a PDF

    :param path:
    :return:
    """
    service = "%s/%s" % (settings.BTE_URL, "make_png_thumbnail")
    with open(path, "rb") as file:
        f = file.read()
    return requests.post(
        url=service,
        files={"file": (os.path.basename(path), f)},
        timeout=60,
    )


def get_page_count(path):
    """Get page count from document

    Sends file to binary-transformers-and-extractors and returns a json
    object containing the pg count

    :param path: path of the document
    :return: {"pg_count: "", "err": ""}
    """
    service = "%s/%s" % (settings.BTE_URL, "get_page_count")
    with open(path, "rb") as file:
        f = file.read()
    try:
        return requests.post(
            url=service,
            files={"file": (os.path.basename(path), f)},
            timeout=60,
        ).json()
    except Timeout:
        return {"err": Timeout}
    except:
        return {"err": "Unknown error occurred"}

import os

import requests
from requests import Timeout

base_url = "http://cl-binary-transformers-and-extractors:80"


def document_extract(path, do_ocr=False):
    """Extract document content.

    :param path:
    :param do_ocr:
    :return:
    """
    service = "%s/%s" % (base_url, "extract_doc_content")
    do_ocr = do_ocr
    with open(path, "rb") as file:
        f = file.read()
    try:
        return requests.post(
            url=service,
            files={"file": (os.path.basename(path), f)},
            params={"do_ocr": do_ocr},
            timeout=3600,
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
    service = "%s/%s" % (base_url, "convert_audio_file")
    with open(path, "rb") as file:
        f = file.read()
    try:
        response = requests.post(
            url=service,
            files={"file": (os.path.basename(path), f)},
            timeout=3600,
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
    service = "%s/%s" % (base_url, "make_png_thumbnail")
    with open(path, "rb") as file:
        f = file.read()
    try:
        response = requests.post(
            url=service,
            files={"file": (os.path.basename(path), f)},
            timeout=300,
        )
        return {"content": response.content, "err": response.headers["err"]}
    except Timeout:
        return {"err": Timeout}
    except:
        return {"err": "Unknown error occurred"}


def get_page_count(path, ext):
    """Get page count from document

    Sends file to binary-transformers-and-extractors and returns a json
    object containing the pg count

    :param path: path of the document
    :param ext: File extension
    :return: {"pg_count: "", "err": ""}
    """
    service = "%s/%s" % (base_url, "get_page_count")
    with open(path, "rb") as file:
        f = file.read()
    try:
        return requests.post(
            url=service,
            files={"file": (os.path.basename(path), f)},
            timeout=300,
        )
    except Timeout:
        return {"err": Timeout}
    except:
        return {"err": "Unknown error occurred"}

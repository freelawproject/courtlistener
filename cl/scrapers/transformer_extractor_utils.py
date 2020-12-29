import json
from typing import Optional, ByteString

import requests
from django.conf import settings


def convert_and_clean_audio(audio_obj) -> requests.Response:
    """Convert audio file to MP3 w/ metadata and image.

    :param audio_obj: Audio file object in db.
    :return: BTE response object
    :type: requests.Response
    """
    date_argued = audio_obj.docket.date_argued
    if date_argued:
        date_argued_str = date_argued.strftime("%Y-%m-%d")
        date_argued_year = date_argued.year
    else:
        date_argued_str, date_argued_year = None, None

    audio_data = {
        "court_full_name": audio_obj.docket.court.full_name,
        "court_short_name": audio_obj.docket.court.short_name,
        "court_pk": audio_obj.docket.court.pk,
        "court_url": audio_obj.docket.court.url,
        "docket_number": audio_obj.docket.docket_number,
        "date_argued": date_argued_str,
        "date_argued_year": date_argued_year,
        "case_name": audio_obj.case_name,
        "case_name_full": audio_obj.case_name_full,
        "case_name_short": audio_obj.case_name_short,
        "download_url": audio_obj.download_url,
    }
    with open(audio_obj.local_path_original_file.path, "rb") as af:
        audio_file = {"audio_file": ("", af.read())}

    bte_audio_response = requests.post(
        settings.BTE_URLS["convert-audio"],
        params={"audio_data": json.dumps(audio_data)},
        files=audio_file,
        timeout=60 * 60,
    )
    return bte_audio_response


def get_page_count(pdf_bytes: bytes) -> Optional[int]:
    """Extract page count from PDF content.

    :param pdf_bytes: PDF bytes
    :return: Page count
    """
    bte_response = requests.post(
        settings.BTE_URLS["page-count"],
        files={"file": ("file.pdf", pdf_bytes)},
    )
    if bte_response.status_code == 200:
        return int(bte_response.content)
    return None


def generate_thumbnail(
    pdf_content: ByteString, max_dimension: int = 350
) -> Optional[ByteString]:
    """Convert PDF bytes into Thumbnail of first page

    :param pdf_content: PDF as bytes
    :param max_dimension: Max dimension for thumbnail
    :return: Generated thumbnail
    """
    thumbnail_response = requests.post(
        settings.BTE_URLS["thumbnail"],
        files={"file": ("thumbnail.png", pdf_content)},
        params={"max_dimension": max_dimension},
    )
    if thumbnail_response.status_code == 200:
        return thumbnail_response.content

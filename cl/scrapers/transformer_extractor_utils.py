import json
from typing import Dict

import requests
from django.conf import settings
from django.core.serializers import serialize


def make_audio_post_params(af) -> Dict:
    """Make audio object parameters used in conversion process.

    BTE requires court and docket information to process the audio. This
    serializes the required information as JSON so we can post it to
    the BTE container.

    :param af: Audio file.
    :return: Audio data in json format
    :type: dict
    """
    af_dict = json.loads(serialize("json", [af]))[0]["fields"]
    docket_dict = json.loads(serialize("json", [af.docket]))[0]["fields"]
    court_dict = json.loads(serialize("json", [af.docket.court]))[0]["fields"]
    af_dict["docket"] = docket_dict
    af_dict["docket"]["court"] = court_dict
    return {"audio_obj": json.dumps(af_dict)}


def convert_and_clean_audio(audio_obj) -> requests.Response:
    """Convert audio file to MP3 w/ metadata and image.

    :param audio_obj: Audio file object
    :return: Request response containing converted audio file w/ duration info.
    :type: requests.Response
    """
    with open(audio_obj.local_path_original_file.path, "rb") as af:
        audio_file = {"file": ("audio_file", af.read())}
    return requests.post(
        url=settings.BTE_URLS["convert_audio"],
        params=make_audio_post_params(audio_obj),
        files=audio_file,
        timeout=60 * 60,
    )

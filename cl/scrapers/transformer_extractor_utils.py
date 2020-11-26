import json

import requests
from django.conf import settings
from django.core.serializers import serialize


def make_audio_post_params(af):
    """Make audio object parameters used in conversion process.

    :param af: Audio file.
    :return: Audio data in json format
    :type: JSON
    """
    af_dict = json.loads(serialize("json", [af]))[0]["fields"]
    docket_dict = json.loads(serialize("json", [af.docket]))[0]["fields"]
    court_dict = json.loads(serialize("json", [af.docket.court]))[0]["fields"]
    af_dict["docket"] = docket_dict
    af_dict["docket"]["court"] = court_dict
    return {"audio_obj": json.dumps(af_dict)}


def convert_and_clean_audio(audio_obj):
    """Convert audio file to MP3 w/ metadata and image.

    :param audio_obj: Audio file object
    :return: Converted audio
    :type: JSON response
    """
    with open(audio_obj.local_path_original_file.path, "rb") as audio_file:
        return requests.post(
            url=settings.BTE_URLS['convert_audio'],
            params=make_audio_post_params(audio_obj),
            files={
                "file": ("audio_file", audio_file.read()),
            },
            timeout=60 * 60,
        )

import json
from tempfile import NamedTemporaryFile

import requests
from django.conf import settings
from django.core import serializers


def serialize_audio_object(af):
    """Convert serialize audio object into json for processing.

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


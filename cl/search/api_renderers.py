import re
from typing import Any

from django.utils.xmlutils import UnserializableContentError
from rest_framework_xml.renderers import XMLRenderer

from cl.lib.redis_utils import get_redis_interface

# Regex for invalid XML characters
INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_xml_data(data: Any) -> Any:
    """
    Recursively clean strings of invalid XML characters

    :param data: the serialized object, or one of its elements
    """
    if isinstance(data, dict):
        return {k: clean_xml_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [clean_xml_data(elem) for elem in data]
    if isinstance(data, str):
        return INVALID_XML_CHARS.sub("", data)

    return data


class SafeXMLRenderer(XMLRenderer):
    """
    A XML renderer that tries to render the data as-is, and if it fails with an
    UnserializableContentError, it cleans the data of invalid XML characters
    and tries again.
    """

    redis_set_name = "api:invalid_xml_chars:opinion_ids"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""

        try:
            return super().render(data, accepted_media_type, renderer_context)
        except UnserializableContentError:
            # Save problematic IDs to Redis for future correction
            r = get_redis_interface("CACHE")

            if isinstance(data, list):
                ids = [i.get("id") for i in data]
            elif isinstance(data, dict):
                ids = [data.get("id")]
            else:
                ids = []

            for object_id in ids:
                if object_id:
                    r.sadd(self.redis_set_name, object_id)

            # clean XML invalid chars and try again
            cleaned_data = clean_xml_data(data)
            return super().render(
                cleaned_data, accepted_media_type, renderer_context
            )

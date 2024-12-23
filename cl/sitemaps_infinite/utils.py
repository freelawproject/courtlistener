from typing import OrderedDict

from django.contrib import sitemaps
from django.utils.module_loading import import_string


def make_sitemaps_list(
    sitemaps: dict[str:str],
) -> OrderedDict[str : sitemaps.Sitemap]:
    """Constructs an OrderedDict of Django Sitemap classes from a dictionary of string keys and string values representing the Sitemap class paths.

    The keys in the input dictionary are the names of the Sitemaps, and the values are the dotted paths to the Sitemap classes.
    This function uses `import_string` to dynamically import the Sitemap classes and return an OrderedDict mapping the names to the Sitemap instances.
    """
    return OrderedDict(
        {import_string(k): import_string(v) for k, v in sitemaps.items()}
    )

from typing import Any
from urllib.parse import urlencode

from django.contrib.contenttypes.admin import GenericTabularInline
from django.db.models import Model
from django.urls import reverse

from cl.lib.models import Note


class AdminTweaksMixin:
    class Media:
        css = {
            "all": ("css/admin.css",),
        }


class NotesInline(GenericTabularInline):
    model = Note
    extra = 1


def build_admin_url(
    model_class: type[Model],
    query_params: dict[str, Any] | None = None,
) -> str:
    """
    Construct a URL for a given model's admin view, optionally appending query parameters.

    :param model_class: The Django model class for which the admin URL will be built.
    :param query_params: A dictionary of query parameters to append to the URL (e.g. {"docket": 123}).
    :return: A string representing the fully constructed admin URL, including any query parameters.

    Example usage:
        >>> from cl.search.models import DocketEntry
        >>> build_admin_url(DocketEntry, {"docket": "1234"})
        '/admin/search/docketentry/?docket=1234'
    """
    query_params = query_params or {}
    app_label = model_class._meta.app_label
    model_name = model_class._meta.model_name
    # "admin:app_label_modelname_changelist" is the standard naming for admin changelist
    entries_changelist_url = reverse(
        f"admin:{app_label}_{model_name}_changelist"
    )
    encoded_query_params = urlencode(query_params)
    return f"{entries_changelist_url}?{encoded_query_params}"

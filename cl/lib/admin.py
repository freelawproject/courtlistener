from typing import Any, TypedDict
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


class AdminLinkConfig(TypedDict):
    label: str
    model_class: type[Model]
    query_params: dict[str, Any] | None


class AdminLink(TypedDict):
    href: str
    label: str


def generate_admin_links(
    links: list[AdminLinkConfig],
) -> list[AdminLink]:
    """
    Construct a list of links with links to given admin views.
    Each link should have the following keys:
    - should_add: Condition to check whether the link should be added.
    - label: Label for the link.
    - model_class: The Django model class for which the admin URL will be built.
    - query_params: Query parameters to append to the URL (e.g. {"docket": 123}).
    """
    generated_links: list[AdminLink] = []

    for link in links:
        generated_links.append(
            {
                "href": build_admin_url(
                    link["model_class"],
                    query_params=link["query_params"],
                ),
                "label": link["label"],
            }
        )

    return generated_links

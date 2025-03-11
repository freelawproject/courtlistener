import logging
from functools import wraps
from typing import Callable

from django.contrib.syndication.views import Feed
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.feedgenerator import Atom1Feed
from django.utils.html import strip_tags
from django.utils.timezone import is_naive
from elasticsearch.exceptions import ApiError, RequestError, TransportError
from elasticsearch_dsl.response import Response

from cl.lib.date_time import midnight_pt
from cl.lib.elasticsearch_utils import do_es_feed_query
from cl.lib.mime_types import lookup_mime_type
from cl.lib.search_index_utils import null_map
from cl.lib.timezone_helpers import localize_naive_datetime_to_court_timezone
from cl.search.documents import ESRECAPDocument, OpinionClusterDocument
from cl.search.exception import (
    BadProximityQuery,
    DisallowedWildcardPattern,
    UnbalancedParenthesesQuery,
    UnbalancedQuotesQuery,
)
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES, Court

logger = logging.getLogger(__name__)


def get_item(item):
    """Normalize grouped and non-grouped results to return the item itself."""
    if "doclist" in item:
        return item["doclist"]["docs"][0]
    else:
        return item


def cleanup_control_chars(
    items: Response, document_text_key: str, jurisdiction: bool = False
) -> None:
    """Clean up control characters from document texts for a proper XML
    rendering.

    :param items: The ES Response containing the search results.
    :param document_text_key: Key in the item dict to clean.
    :param jurisdiction: A bool to indicate if the item is from a jurisdiction
    feed.
    :return: None. The function modify items in place.
    """

    for item in items:
        if document_text_key == "text":
            # Opinions case.
            if jurisdiction:
                # Jurisdiction Feed display Opinions
                item[document_text_key] = strip_tags(
                    item[document_text_key][0].translate(null_map)
                )
            else:
                # Opinions Search Feed display Clusters with child summary.
                for doc in item.child_docs:
                    doc["_source"][document_text_key] = strip_tags(
                        doc["_source"][document_text_key][0].translate(
                            null_map
                        )
                    )
        else:
            # RECAP Search Feed. Display RECAPDocuments instead of Dockets.
            item[document_text_key] = strip_tags(
                item[document_text_key][0].translate(null_map)
            )


class SearchFeed(Feed):
    """This feed returns the results of a search feed. It lacks a second
    argument in the method b/c it gets its search query from a GET request.
    """

    feed_type = Atom1Feed
    title = "CourtListener.com Custom Search Feed"
    link = "https://www.courtlistener.com/"
    author_name = "Free Law Project"
    author_email = "feeds@courtlistener.com"
    description_template = "feeds/description_template.html"
    feed_copyright = "Created for the public domain by Free Law Project"

    def get_object(self, request, get_string):
        return request

    def items(self, obj):
        """Do a search query here. Return the first 20 results.
        For Opinions SearchFeed returns clusters.
        For RECAP SearchFeed returns RECAPDocuments.
        """
        search_form = SearchForm(obj.GET)
        if not search_form.is_valid():
            return []

        cd = search_form.cleaned_data
        order_by = "dateFiled"
        match cd["type"]:
            case SEARCH_TYPES.OPINION:
                document_text_key = "text"
                es_search_query = OpinionClusterDocument.search()
                override_params = {
                    "order_by": f"{order_by} desc",
                }
                exclude_docs_for_empty_field = order_by
            case SEARCH_TYPES.RECAP:
                document_text_key = "plain_text"
                es_search_query = ESRECAPDocument.search()
                override_params = {
                    "order_by": "entry_date_filed_feed desc",
                }
                exclude_docs_for_empty_field = "entry_date_filed"
            case _:
                return []

        cd.update(override_params)
        items = do_es_feed_query(
            es_search_query,
            cd,
            rows=20,
            exclude_docs_for_empty_field=exclude_docs_for_empty_field,
        )
        cleanup_control_chars(items, document_text_key)
        return items

    def item_link(self, item):
        return get_item(item)["absolute_url"]

    def item_author_name(self, item):
        return get_item(item)["court"]

    def item_pubdate(self, item):
        try:
            # Get pub_date for RECAP
            entry_date = get_item(item)["entry_date_filed"]
            if not is_naive(entry_date):
                # Handle non-naive dates
                return midnight_pt(entry_date)
            else:
                return localize_naive_datetime_to_court_timezone(
                    get_item(item)["court_id"], entry_date
                )
        except KeyError:
            # Get pub_date for Opinions
            return midnight_pt(get_item(item)["dateFiled"])

    def item_title(self, item):
        return get_item(item)["caseName"]


class JurisdictionFeed(Feed):
    """When working on this feed, note that it is overridden in a number of
    places, so changes here may have unintended consequences.
    """

    feed_type = Atom1Feed
    link = "https://www.courtlistener.com/"
    author_name = "Free Law Project"
    author_email = "feeds@courtlistener.com"
    feed_copyright = "Created for the public domain by Free Law Project"
    description_template = "feeds/description_template.html"

    def title(self, obj):
        return f"CourtListener.com: All opinions for the {obj.full_name}"

    def get_object(self, request, court):
        return get_object_or_404(Court, pk=court)

    def items(self, obj):
        """Do a search query here. Return the first 20 results
        JurisdictionFeed return Opinions instead of Clusters.
        """
        es_search_query = OpinionClusterDocument.search()
        cd = {
            "court": obj.pk,
            "order_by": "dateFiled desc",
            "type": SEARCH_TYPES.OPINION,
        }
        items = do_es_feed_query(
            es_search_query, cd, rows=20, jurisdiction=True
        )
        cleanup_control_chars(items, "text", jurisdiction=True)
        return items

    def item_link(self, item):
        return get_item(item)["absolute_url"]

    def item_author_name(self, item):
        return get_item(item)["court"]

    def item_pubdate(self, item):
        return midnight_pt(get_item(item)["dateFiled"])

    def item_title(self, item):
        return get_item(item)["caseName"]

    def item_categories(self, item):
        return [get_item(item)["status"]]

    def item_enclosure_url(self, item):
        try:
            path = get_item(item)["local_path"]
            return f"https://storage.courtlistener.com/{path}"
        except:
            return None

    def item_enclosure_mime_type(self, item):
        try:
            path = get_item(item)["local_path"]
            return lookup_mime_type(path)
        except:
            return None

    # See: https://validator.w3.org/feed/docs/error/UseZeroForUnknown.html
    item_enclosure_length = 0


class AllJurisdictionsFeed(JurisdictionFeed):
    title = "CourtListener.com: All Opinions (High Volume)"

    def get_object(self, request):
        return None

    def items(self, obj):
        """Do a match all search query. Return the first 20 results"""
        es_search_query = OpinionClusterDocument.search()
        cd = {
            "order_by": "dateFiled desc",
            "type": SEARCH_TYPES.OPINION,
        }
        items = do_es_feed_query(
            es_search_query, cd, rows=20, jurisdiction=True
        )
        cleanup_control_chars(items, "text", jurisdiction=True)
        return items


def search_feed_error_handler(view_func: Callable) -> Callable:
    """Wraps a Feed view function to handle search feed errors gracefully.

    :param view_func: The Feed view to be wrapped.
    :return: The wrapped view function that handles search feed errors.
    """

    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        try:
            response = view_func(request, *args, **kwargs)
            return response
        except (
            UnbalancedParenthesesQuery,
            UnbalancedQuotesQuery,
            BadProximityQuery,
            DisallowedWildcardPattern,
            ApiError,
        ) as e:
            logger.warning("Couldn't load the feed page. Error was: %s", e)
            return HttpResponse(
                "Invalid search syntax. Please check your request and try again.",
                status=400,
            )

        except (TransportError, ConnectionError, RequestError) as e:
            logger.warning("Couldn't load the feed page. Error was: %s", e)
            return HttpResponse(
                "Unable to process your request. Please try again later.",
                status=500,
            )

    return wrapped_view

from datetime import datetime

import waffle
from django.contrib.syndication.views import Feed
from django.db.models import QuerySet
from django.http import Http404, HttpRequest
from django.utils.feedgenerator import Atom1Feed
from django.utils.safestring import SafeText, mark_safe

from cl.lib.date_time import midnight_pt
from cl.opinion_page.docket_sources_utils import SCOTUS_SOURCE
from cl.opinion_page.utils import make_docket_title
from cl.search.models import Docket, DocketEntry, SCOTUSDocketEntry


class DocketFeed(Feed):
    """This feed returns the results of a search feed. It lacks a second
    argument in the method b/c it gets its search query from a GET request.
    """

    feed_type = Atom1Feed
    link = "https://www.courtlistener.com/"
    author_name = "Free Law Project"
    author_email = "feeds@courtlistener.com"
    feed_copyright = "Created for the public domain by Free Law Project"
    item_enclosure_mimetype = "application/pdf"

    def title(self, obj: Docket) -> str:
        return f"Docket updates for {make_docket_title(obj)}"

    def get_object(self, request: HttpRequest, docket_id: int) -> Docket:  # type: ignore
        """Return the docket the feed is for, or raise Http404.

        SCOTUS dockets 404 while the ``scotus_docket_page`` waffle flag is
        off."""
        try:
            d = Docket.objects.only(
                "case_name",
                "case_name_short",
                "case_name_full",
                "docket_number",
                # For get_entry_source()
                "court_id",
                # For item_link()'s get_absolute_url()
                "slug",
            ).get(pk=docket_id)
        except Docket.DoesNotExist:
            raise Http404("Unable to find docket")

        if d.get_entry_source() is SCOTUS_SOURCE and not waffle.flag_is_active(
            request, "scotus_docket_page"
        ):
            raise Http404("Unable to find docket")

        return d

    def items(
        self, obj: Docket
    ) -> QuerySet[DocketEntry] | QuerySet[SCOTUSDocketEntry]:
        """Return the docket's 30 most recent dated entries for the feed."""
        source = obj.get_entry_source()
        return (
            source.entries_queryset(obj)
            # entries_queryset() prefetches every document for the docket
            # page; the feed only reads main_docs, so drop that and attach
            # just the one-doc-per-entry prefetch.
            .prefetch_related(None)
            .exclude(date_filed__isnull=True)
            .prefetch_related(source.main_docs_prefetch())
            .order_by(*source.order_by_desc)[:30]
        )

    def item_title(self, item: DocketEntry | SCOTUSDocketEntry) -> SafeText:
        docket_title = make_docket_title(item.docket)
        entry_number = item.entry_number
        if entry_number:
            preface = f"Entry #{entry_number}"
        else:
            preface = f"Minute entry from {item.date_filed}"
        return mark_safe(f"{preface} in {docket_title}")

    def item_description(self, item: DocketEntry | SCOTUSDocketEntry) -> str:
        try:
            # main_docs comes from the source's main_docs_prefetch()
            main_doc = item.main_docs[0]
        except IndexError:
            # No doc associated with entry
            return item.description
        return item.description or main_doc.description

    def item_link(self, item: DocketEntry | SCOTUSDocketEntry) -> str:
        if item.entry_number:
            anchor = f"entry-{item.entry_number}"
        else:
            anchor = f"minute-entry-{item.pk}"
        return f"{item.docket.get_absolute_url()}?order_by=desc#{anchor}"

    def item_pubdate(self, item: DocketEntry | SCOTUSDocketEntry) -> datetime:
        return midnight_pt(item.date_filed)

    def item_enclosure_url(
        self, item: DocketEntry | SCOTUSDocketEntry
    ) -> str | None:
        if not item.entry_number:
            return None

        # If we don't have a representative document, abort.
        try:
            main_doc = item.main_docs[0]
        except IndexError:
            # No docs with entry
            return None

        # Serve the PDF if we have it
        path = main_doc.filepath_local
        if path:
            return f"https://storage.courtlistener.com/{path}"

        # If we don't have the PDF, serve a link to the source's own
        # external URL.
        source = item.docket.get_entry_source()
        return source.document_external_url(main_doc)

    # See: https://validator.w3.org/feed/docs/error/UseZeroForUnknown.html
    item_enclosure_length = 0

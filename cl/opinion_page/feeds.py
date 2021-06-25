from datetime import datetime
from typing import Optional

from django.contrib.syndication.views import Feed
from django.db.models import Prefetch, QuerySet
from django.http import Http404, HttpRequest
from django.utils.feedgenerator import Atom1Feed
from django.utils.safestring import SafeText, mark_safe

from cl.lib.date_time import midnight_pst
from cl.opinion_page.views import make_docket_title
from cl.search.models import Docket, DocketEntry, RECAPDocument


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
        try:
            d = Docket.objects.only(
                "case_name",
                "case_name_short",
                "case_name_full",
                "docket_number",
            ).get(pk=docket_id)
        except Docket.DoesNotExist:
            raise Http404("Unable to find docket")
        else:
            return d

    def items(self, obj: Docket) -> QuerySet:
        # Get the items with prefetched main-docs
        main_docs_query = (
            RECAPDocument.objects.filter(
                document_type=RECAPDocument.PACER_DOCUMENT
            )
            .only("description")
            .order_by("date_created")
        )
        return (
            DocketEntry.objects.filter(docket=obj)
            .prefetch_related(
                Prefetch(
                    "recap_documents",
                    queryset=main_docs_query,
                    to_attr="main_docs",
                )
            )
            .select_related("docket")
            .order_by("-recap_sequence_number", "-entry_number")
            .only(
                "description",
                "entry_number",
                "date_filed",
                # For `item_link`
                "docket__id",
                "docket__slug",
                # For `item_title`
                "docket__case_name",
                "docket__case_name_full",
                "docket__case_name_short",
                "docket__docket_number",
            )
        )

    def item_title(self, item: DocketEntry) -> SafeText:
        docket_title = make_docket_title(item.docket)
        return mark_safe(f"Entry #{item.entry_number} in {docket_title}")

    def item_description(self, item: DocketEntry) -> str:
        try:
            # main_docs comes from the to_attr parameter above
            main_rd = item.main_docs[0]
        except IndexError:
            # No doc associated with entry
            return item.description
        return item.description or main_rd.description

    def item_link(self, item: DocketEntry) -> str:
        return f"{item.docket.get_absolute_url()}?order_by=desc#entry-{item.entry_number}"

    def item_pubdate(self, item: DocketEntry) -> datetime:
        return midnight_pst(item.date_filed)

    def item_enclosure_url(self, item: DocketEntry) -> Optional[str]:
        if not item.entry_number:
            return None

        # If we don't have the rd, abort.
        try:
            main_rd = item.main_docs[0]
        except IndexError:
            # No docs with entry
            return None

        # Serve the PDF if we have it
        path = main_rd.filepath_local
        if path:
            return f"https://storage.courtlistener.com/{path}"

        # If we don't have the PDF, serve a link to PACER
        if main_rd.pacer_url:
            return main_rd.pacer_url

        return None

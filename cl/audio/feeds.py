"""Podcast feeds of oral argument audio."""

from django.shortcuts import get_object_or_404
from django.templatetags.static import static
from django.utils.timezone import is_naive

from cl.lib.elasticsearch_utils import do_es_feed_query
from cl.lib.podcast import iTunesPodcastsFeedGenerator
from cl.lib.timezone_helpers import localize_naive_datetime_to_court_timezone
from cl.search.documents import AudioDocument
from cl.search.feeds import JurisdictionFeed, get_item
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES, Court


class JurisdictionPodcast(JurisdictionFeed):
    """Podcast of the 20 most recently argued oral arguments in a court."""

    feed_type = iTunesPodcastsFeedGenerator
    iTunes_name = "Free Law Project"
    iTunes_email = "feeds@courtlistener.com"
    iTunes_image_url = f"{static('png/producer-2000x2000.png')}"
    iTunes_explicit = "no"
    item_enclosure_mime_type = "audio/mpeg"

    def title(self, obj):
        """Title the feed as the oral arguments for the court."""
        _, court = obj
        return f"Oral Arguments for the {court.full_name}"

    def description(self, obj):
        """Describe the podcast."""
        return (
            "A chronological podcast of oral arguments with improved "
            "files and meta data. Hosted by Free Law Project through "
            "the CourtListener.com initiative. Not an official podcast."
        )

    subtitle = description

    def get_object(self, request, court):
        """Get the request and the court, or raise 404 if the court doesn't exist."""
        return request, get_object_or_404(Court, pk=court)

    def items(self, obj):
        """Returns a list of items to publish in this feed."""
        request, court = obj
        cd = {
            "q": "*",
            "court": court.pk,
            "order_by": "dateArgued desc",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        search_query = AudioDocument.search()
        return do_es_feed_query(
            search_query,
            cd,
            rows=20,
            exclude_docs_for_empty_field="local_path",
        )

    def feed_extra_kwargs(self, obj):
        """Add the iTunes name, email, explicit flag, and image URL to the feed."""
        extra_args = {
            "iTunes_name": self.iTunes_name,
            "iTunes_email": self.iTunes_email,
            "iTunes_explicit": self.iTunes_explicit,
        }
        img_path = static("png/producer-2000x2000.png")
        extra_args["iTunes_image_url"] = (
            f"https://storage.courtlistener.com{img_path}"
        )

        return extra_args

    def item_extra_kwargs(self, item):
        """Add the court as author, the duration, and the explicit flag to an item."""
        return {
            "author": get_item(item)["court"],
            "duration": str(item["duration"]),
            "explicit": "no",
        }

    def item_enclosure_url(self, item):
        """Link to the item's audio file in storage."""
        path = get_item(item)["local_path"]
        return f"https://storage.courtlistener.com/{path}"

    def item_enclosure_length(self, item):
        """Get the size of the item's MP3 file."""
        return get_item(item)["file_size_mp3"]

    def item_pubdate(self, item):
        """Get the item's argument date, localized to the court's timezone if naive."""
        pub_date = get_item(item)["dateArgued"]
        if not pub_date:
            return None
        if is_naive(pub_date):
            pub_date = localize_naive_datetime_to_court_timezone(
                get_item(item)["court"], pub_date
            )
        return pub_date

    description_template = None

    def item_description(self, item):
        """Describe the item with its case name."""
        return get_item(item)["caseName"]

    def item_categories(self, item):
        """Give items no categories."""
        return None


class AllJurisdictionsPodcast(JurisdictionPodcast):
    """Podcast of the 20 most recently argued oral arguments in any court."""

    def title(self, obj):
        """Title the feed as covering all oral arguments."""
        return (
            "CourtListener.com: Podcast of All Oral Arguments available in "
            "the Federal Circuit Courts (High Volume)"
        )

    def get_object(self, request):
        """Use the request as the feed's object."""
        return request

    def items(self, obj):
        """Get the 20 most recently argued oral arguments that have audio."""
        cd = {
            "q": "*",
            "order_by": "dateArgued desc",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        search_query = AudioDocument.search()
        return do_es_feed_query(
            search_query,
            cd,
            rows=20,
            exclude_docs_for_empty_field="local_path",
        )


class SearchPodcast(JurisdictionPodcast):
    """Podcast of the 20 most recently argued oral arguments matching a search."""

    def _get_search_summary(self, request):
        """Build a human-readable search summary from GET params.

        Caches on the request to avoid re-parsing the form in
        title/description/subtitle.
        """
        if hasattr(request, "_summary_cache"):
            return request._summary_cache

        summary = ""
        search_form = SearchForm(request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            courts: list[bool] = [
                v for k, v in cd.items() if k.startswith("court_")
            ]
            selected = courts.count(True)
            court_count_human = (
                "All" if selected == len(courts) else str(selected)
            )
            summary = search_form.as_text(court_count_human)

        request._summary_cache = summary
        return summary

    def title(self, obj):
        """Title the feed, including a summary of the search when there is one."""
        if summary := self._get_search_summary(obj):
            return f"{summary} — CourtListener Oral Arguments"
        return "CourtListener.com Custom Oral Argument Podcast"

    def description(self, obj):
        """Describe the feed, including a summary of the search when there is one."""
        if summary := self._get_search_summary(obj):
            return (
                f"Oral arguments matching: {summary}. "
                "A custom podcast by Free Law Project via "
                "CourtListener.com."
            )
        return (
            "A chronological podcast of oral arguments with improved "
            "files and meta data. Hosted by Free Law Project through "
            "the CourtListener.com initiative."
        )

    def subtitle(self, obj):
        """Use the description as the subtitle."""
        return self.description(obj)

    def get_object(self, request, court):
        """Use the request as the feed's object."""
        return request

    def items(self, obj):
        """Get the 20 most recently argued oral arguments with audio that match the search.

        An invalid search returns no items.
        """
        search_form = SearchForm(obj.GET)
        if not search_form.is_valid():
            return []
        cd = search_form.cleaned_data
        override_params = {
            "order_by": "dateArgued desc",
        }
        cd.update(override_params)
        search_query = AudioDocument.search()
        return do_es_feed_query(
            search_query,
            cd,
            rows=20,
            exclude_docs_for_empty_field="local_path",
        )

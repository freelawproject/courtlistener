import waffle
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.templatetags.static import static
from django.utils.timezone import is_naive
from requests import Session

from cl.lib import search_utils
from cl.lib.elasticsearch_utils import do_es_podcast_query
from cl.lib.podcast import iTunesPodcastsFeedGenerator
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.timezone_helpers import localize_naive_datetime_to_court_timezone
from cl.search.documents import AudioDocument
from cl.search.feeds import JurisdictionFeed, get_item
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES, Court


class JurisdictionPodcast(JurisdictionFeed):
    feed_type = iTunesPodcastsFeedGenerator
    description = (
        "A chronological podcast of oral arguments with improved "
        "files and meta data. Hosted by Free Law Project through "
        "the CourtListener.com initiative. Not an official podcast."
    )
    subtitle = description
    summary = description
    iTunes_name = "Free Law Project"
    iTunes_email = "feeds@courtlistener.com"
    iTunes_image_url = f"https://storage.courtlistener.com{static('png/producer-2000x2000.png')}"
    iTunes_explicit = "no"
    item_enclosure_mime_type = "audio/mpeg"

    def title(self, obj):
        _, court = obj
        return f"Oral Arguments for the {court.full_name}"

    def get_object(self, request, court):
        return request, get_object_or_404(Court, pk=court)

    def items(self, obj):
        """
        Returns a list of items to publish in this feed.
        """
        request, court = obj
        if waffle.flag_is_active(request, "oa-es-deactivate"):
            with Session() as session:
                solr = ExtraSolrInterface(
                    settings.SOLR_AUDIO_URL, http_connection=session, mode="r"
                )
                params = {
                    "q": "*",
                    "fq": f"court_exact:{court.pk}",
                    "sort": "dateArgued desc",
                    "rows": "20",
                    "start": "0",
                    "caller": "JurisdictionPodcast",
                }
                items = solr.query().add_extra(**params).execute()
                return items
        else:
            cd = {
                "q": "*",
                "court": court.pk,
                "order_by": "dateArgued desc",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
            }
            search_query = AudioDocument.search()
            items = do_es_podcast_query(search_query, cd, rows=20)
            return items

    def feed_extra_kwargs(self, obj):
        extra_args = {
            "iTunes_name": self.iTunes_name,
            "iTunes_email": self.iTunes_email,
            "iTunes_explicit": self.iTunes_explicit,
        }
        if isinstance(obj, tuple) and hasattr(obj[1], "pk"):
            path = static(f"png/producer-{obj[1].pk}-2000x2000.png")
        else:
            # Not a jurisdiction API -- A search API.
            path = static("png/producer-2000x2000.png")
        extra_args[
            "iTunes_image_url"
        ] = f"https://storage.courtlistener.com{path}"

        return extra_args

    def item_extra_kwargs(self, item):
        return {
            "author": get_item(item)["court"],
            "duration": str(item["duration"]),
            "explicit": "no",
        }

    def item_enclosure_url(self, item):
        path = get_item(item)["local_path"]
        return f"https://storage.courtlistener.com/{path}"

    def item_enclosure_length(self, item):
        return get_item(item)["file_size_mp3"]

    def item_pubdate(self, item):
        pub_date = get_item(item)["dateArgued"]
        if is_naive(pub_date):
            pub_date = localize_naive_datetime_to_court_timezone(
                get_item(item)["court"], pub_date
            )
        return pub_date

    description_template = None

    def item_description(self, item):
        return get_item(item)["caseName"]

    def item_categories(self, item):
        return None


class AllJurisdictionsPodcast(JurisdictionPodcast):
    title = (
        "CourtListener.com: Podcast of All Oral Arguments available in "
        "the Federal Circuit Courts (High Volume)"
    )

    def get_object(self, request):
        return request

    def items(self, obj):
        if waffle.flag_is_active(obj, "oa-es-deactivate"):
            with Session() as session:
                solr = ExtraSolrInterface(
                    settings.SOLR_AUDIO_URL, http_connection=session, mode="r"
                )
                params = {
                    "q": "*",
                    "sort": "dateArgued desc",
                    "rows": "20",
                    "start": "0",
                    "caller": "AllJurisdictionsPodcast",
                }
                items = solr.query().add_extra(**params).execute()
                return items
        else:
            cd = {
                "q": "*",
                "order_by": "dateArgued desc",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
            }
            search_query = AudioDocument.search()
            items = do_es_podcast_query(search_query, cd, rows=20)
            return items


class SearchPodcast(JurisdictionPodcast):
    title = "CourtListener.com Custom Oral Argument Podcast"

    def get_object(self, request, get_string):
        return request

    def items(self, obj):
        search_form = SearchForm(obj.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            if waffle.flag_is_active(obj, "oa-es-deactivate"):
                with Session() as session:
                    solr = ExtraSolrInterface(
                        settings.SOLR_AUDIO_URL,
                        http_connection=session,
                        mode="r",
                    )
                    main_params = search_utils.build_main_query(
                        cd, highlight=False, facet=False
                    )
                    main_params.update(
                        {
                            "sort": "dateArgued desc",
                            "rows": "20",
                            "start": "0",
                            "caller": "SearchFeed",
                        }
                    )
                    items = solr.query().add_extra(**main_params).execute()
                    return items
            else:
                override_params = {
                    "order_by": "dateArgued desc",
                }
                search_query = AudioDocument.search()
                items = do_es_podcast_query(
                    search_query,
                    cd,
                    override_params,
                    rows=20,
                )
                return items
        else:
            return []

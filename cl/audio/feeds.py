from django.conf import settings
from django.templatetags.static import static
from requests import Session

from cl.lib import search_utils
from cl.lib.podcast import iTunesPodcastsFeedGenerator
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.search.feeds import JurisdictionFeed, get_item
from cl.search.forms import SearchForm


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
        return f"Oral Arguments for the {obj.full_name}"

    def items(self, obj):
        """
        Returns a list of items to publish in this feed.
        """
        with Session() as session:
            solr = ExtraSolrInterface(
                settings.SOLR_AUDIO_URL, http_connection=session, mode="r"
            )
            params = {
                "q": "*",
                "fq": f"court_exact:{obj.pk}",
                "sort": "dateArgued desc",
                "rows": "20",
                "start": "0",
                "caller": "JurisdictionPodcast",
            }
            items = solr.query().add_extra(**params).execute()
            return items

    def feed_extra_kwargs(self, obj):
        extra_args = {
            "iTunes_name": "Free Law Project",
            "iTunes_email": "feeds@courtlistener.com",
            "iTunes_explicit": "no",
        }
        if hasattr(obj, "pk"):
            path = static(f"png/producer-{obj.pk}-2000x2000.png")
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
        return get_item(item)["dateArgued"]

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
        return None

    def items(self, obj):
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


class SearchPodcast(JurisdictionPodcast):
    title = "CourtListener.com Custom Oral Argument Podcast"

    def get_object(self, request, get_string):
        return request

    def items(self, obj):
        search_form = SearchForm(obj.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            with Session() as session:
                solr = ExtraSolrInterface(
                    settings.SOLR_AUDIO_URL, http_connection=session, mode="r"
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
            return []

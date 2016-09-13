from django.conf import settings

from cl.lib import search_utils, sunburnt
from cl.lib.podcast import iTunesPodcastsFeedGenerator
from cl.search.feeds import JurisdictionFeed
from cl.search.forms import SearchForm


class JurisdictionPodcast(JurisdictionFeed):
    feed_type = iTunesPodcastsFeedGenerator
    description = ("A chronological podcast of oral arguments with improved "
                   "files and meta data. Hosted by Free Law Project through "
                   "the CourtListener.com initiative. Not an official podcast.")
    subtitle = description
    summary = description
    iTunes_name = u'Free Law Project'
    iTunes_email = u'feeds@courtlistener.com'
    iTunes_image_url = u'https://www.courtlistener.com/static/png/producer-2000x2000.png'
    iTunes_explicit = u'no'

    def title(self, obj):
        return "Oral Arguments for the %s" % obj.full_name

    def items(self, obj):
        """
        Returns a list of items to publish in this feed.
        """
        conn = sunburnt.SolrInterface(settings.SOLR_AUDIO_URL, mode='r')
        params = {
            'q': '*',
            'fq': 'court_exact:%s' % obj.pk,
            'sort': 'dateArgued desc',
            'rows': '20',
            'start': '0',
            'caller': 'JurisdictionPodcast',
        }
        return conn.raw_query(**params).execute()

    def feed_extra_kwargs(self, obj):
        extra_args = {
            'iTunes_name': u'Free Law Project',
            'iTunes_email': u'feeds@courtlistener.com',
            'iTunes_explicit': u'no',
        }
        if hasattr(obj, 'pk'):
            path = u'/static/png/producer-%s-2000x2000.png' % obj.pk
        else:
            # Not a jurisdiction API -- A search API.
            path = u'/static/png/producer-2000x2000.png'
        extra_args['iTunes_image_url'] = 'https://www.courtlistener.com%s' % path

        return extra_args

    def item_extra_kwargs(self, item):
        return {'author': item['court'],
                'duration': str(item['duration']),
                'explicit': u'no'}

    def item_enclosure_url(self, item):
        return 'https://www.courtlistener.com/%s' % item['local_path']

    def item_enclosure_length(self, item):
        return item['file_size_mp3']

    def item_pubdate(self, item):
        return item['dateArgued']

    description_template = None
    def item_description(self, item):
        return item['caseName']

    def item_categories(self, item):
        return None

    item_enclosure_mime_type = u'audio/mpeg'


class AllJurisdictionsPodcast(JurisdictionPodcast):
    title = ("CourtListener.com: Podcast of All Oral Arguments available in "
             "the Federal Circuit Courts (High Volume)")

    def get_object(self, request):
        return None

    def items(self, obj):
        conn = sunburnt.SolrInterface(settings.SOLR_AUDIO_URL, mode='r')
        params = {
            'q': '*',
            'sort': 'dateArgued desc',
            'rows': '20',
            'start': '0',
            'caller': 'AllJurisdictionsPodcast',
        }
        return conn.raw_query(**params).execute()


class SearchPodcast(JurisdictionPodcast):
    title = "CourtListener.com Custom Oral Argument Podcast"

    def get_object(self, request, get_string):
        return request

    def items(self, obj):
        search_form = SearchForm(obj.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            conn = sunburnt.SolrInterface(settings.SOLR_AUDIO_URL, mode='r')
            main_params = search_utils.build_main_query(cd, highlight=False)
            main_params.update({
                'sort': 'dateArgued desc',
                'rows': '20',
                'start': '0',
                'caller': 'SearchFeed',
            })
            return conn.raw_query(**main_params).execute()
        else:
            return []

import datetime
from cl.lib import search_utils, sunburnt
from cl.search.forms import SearchForm
from cl.search.models import Court
from django.conf import settings
from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.utils.feedgenerator import Atom1Feed


class SearchFeed(Feed):
    """This feed returns the results of a search feed. It lacks a second
    argument in the method b/c it gets its search query from a GET request.
    """
    feed_type = Atom1Feed
    title = "CourtListener.com Custom Search Feed"
    link = "https://www.courtlistener.com"
    author_name = "Free Law Project"
    author_email = "feeds@courtlistener.com"
    description_template = 'feeds/solr_desc_template.html'
    feed_copyright = "Created for the public domain by Free Law Project"

    def get_object(self, request, get_string):
        return request

    def items(self, obj):
        """Do a Solr query here. Return the first 20 results"""
        search_form = SearchForm(obj.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
            main_params = search_utils.build_main_query(cd, highlight=False)
            main_params.update({
                'sort': 'dateFiled desc',
                'rows': '20',
                'start': '0',
                'caller': 'SearchFeed',
            })
            return conn.raw_query(**main_params).execute()
        else:
            return []

    def item_link(self, item):
        return item['absolute_url']

    def item_author_name(self, item):
        return item['court']

    def item_pubdate(self, item):
        return datetime.datetime.combine(item['dateFiled'], datetime.time())

    def item_title(self, item):
        return item['caseName']


class JurisdictionFeed(Feed):
    """When working on this feed, note that it is overridden in a number of
    places, so changes here may have unintended consequences.
    """
    feed_type = Atom1Feed
    link = 'https://www.courtlistener.com'
    author_name = "Free Law Project"
    author_email = "feeds@courtlistener.com"
    feed_copyright = "Created for the public domain by Free Law Project"

    def title(self, obj):
        return "CourtListener.com: All opinions for the " + obj.full_name

    def get_object(self, request, court):
        return get_object_or_404(Court, pk=court)

    def items(self, obj):
        """Do a Solr query here. Return the first 20 results"""
        conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
        params = {
            'q': '*:*',
            'fq': 'court_exact:%s' % obj.pk,
            'sort': 'dateFiled desc',
            'rows': '20',
            'start': '0',
            'caller': 'JurisdictionFeed',
        }
        return conn.raw_query(**params).execute()

    def item_link(self, item):
        return item['absolute_url']

    def item_author_name(self, item):
        return item['court']

    def item_pubdate(self, item):
        return datetime.datetime.combine(item['dateFiled'], datetime.time())

    def item_title(self, item):
        return item['caseName']

    def item_categories(self, item):
        return [item['status'], ]

    def item_enclosure_url(self, item):
        path = item['local_path']
        if not path.startswith('/'):
            return '/%s' % (path,)
        return path

    description_template = 'feeds/solr_desc_template.html'


class AllJurisdictionsFeed(JurisdictionFeed):
    title = "CourtListener.com: All Opinions (High Volume)"

    def get_object(self, request):
        return None

    def items(self, obj):
        """Do a Solr query here. Return the first 20 results"""
        conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
        params = {
            'q': '*:*',
            'sort': 'dateFiled desc',
            'rows': '20',
            'start': '0',
            'caller': 'AllJurisdictionsFeed',
        }
        return conn.raw_query(**params).execute()

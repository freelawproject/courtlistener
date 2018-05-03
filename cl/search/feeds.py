import datetime
import os

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.utils.feedgenerator import Atom1Feed

from cl.lib import search_utils
from cl.lib.mime_types import lookup_mime_type
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.search.forms import SearchForm
from cl.search.models import Court


def get_item(item):
    """Normalize grouped and non-grouped results to return the item itself."""
    if 'doclist' in item:
        return item['doclist']['docs'][0]
    else:
        return item


class SearchFeed(Feed):
    """This feed returns the results of a search feed. It lacks a second
    argument in the method b/c it gets its search query from a GET request.
    """
    feed_type = Atom1Feed
    title = "CourtListener.com Custom Search Feed"
    link = "https://www.courtlistener.com/"
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
            order_by = 'dateFiled'
            if cd['type'] == 'o':
                solr = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode='r')
            elif cd['type'] == 'r':
                solr = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode='r')
            else:
                return []
            main_params = search_utils.build_main_query(cd, highlight=False,
                                                        facet=False)
            main_params.update({
                'sort': '%s desc' % order_by,
                'rows': '20',
                'start': '0',
                'caller': 'SearchFeed',
            })
            # Eliminate items that lack the ordering field.
            main_params['fq'].append('%s:[* TO *]' % order_by)
            return solr.query().add_extra(**main_params).execute()
        else:
            return []

    def item_link(self, item):
        return get_item(item)['absolute_url']

    def item_author_name(self, item):
        return get_item(item)['court']

    def item_pubdate(self, item):
        return datetime.datetime.combine(get_item(item)['dateFiled'],
                                         datetime.time())

    def item_title(self, item):
        return get_item(item)['caseName']


class JurisdictionFeed(Feed):
    """When working on this feed, note that it is overridden in a number of
    places, so changes here may have unintended consequences.
    """
    feed_type = Atom1Feed
    link = 'https://www.courtlistener.com/'
    author_name = "Free Law Project"
    author_email = "feeds@courtlistener.com"
    feed_copyright = "Created for the public domain by Free Law Project"
    description_template = 'feeds/solr_desc_template.html'

    def title(self, obj):
        return "CourtListener.com: All opinions for the " + obj.full_name

    def get_object(self, request, court):
        return get_object_or_404(Court, pk=court)

    def items(self, obj):
        """Do a Solr query here. Return the first 20 results"""
        solr = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode='r')
        params = {
            'q': '*',
            'fq': 'court_exact:%s' % obj.pk,
            'sort': 'dateFiled desc',
            'rows': '20',
            'start': '0',
            'caller': 'JurisdictionFeed',
        }
        return solr.query().add_extra(**params).execute()

    def item_link(self, item):
        return get_item(item)['absolute_url']

    def item_author_name(self, item):
        return get_item(item)['court']

    def item_pubdate(self, item):
        return datetime.datetime.combine(get_item(item)['dateFiled'],
                                         datetime.time())

    def item_title(self, item):
        return get_item(item)['caseName']

    def item_categories(self, item):
        return [get_item(item)['status']]

    def item_enclosure_url(self, item):
        try:
            path = get_item(item)['local_path']
            if not path.startswith('/'):
                return '/%s' % (path,)
            return path
        except:
            return None

    def item_enclosure_length(self, item):
        try:
            file_loc = os.path.join(
                settings.MEDIA_ROOT,
                get_item(item)['local_path'].encode('utf-8')
            )
            return os.path.getsize(file_loc)
        except:
            return None

    def item_enclosure_mime_type(self, item):
        try:
            file_loc = os.path.join(
                settings.MEDIA_ROOT,
                get_item(item)['local_path'].encode('utf-8')
            )
            return lookup_mime_type(file_loc)
        except:
            return None


class AllJurisdictionsFeed(JurisdictionFeed):
    title = "CourtListener.com: All Opinions (High Volume)"

    def get_object(self, request):
        return None

    def items(self, obj):
        """Do a Solr query here. Return the first 20 results"""
        solr = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode='r')
        params = {
            'q': '*',
            'sort': 'dateFiled desc',
            'rows': '20',
            'start': '0',
            'caller': 'AllJurisdictionsFeed',
        }
        return solr.query().add_extra(**params).execute()

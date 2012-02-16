# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.contrib.syndication.views import FeedDoesNotExist
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from django.utils import feedgenerator
from django.utils.feedgenerator import Atom1Feed

from alert.lib import search_utils
from alert.search.forms import SearchForm
from alert.search.models import Court, Document
from alert.lib import sunburnt


class search_feed(Feed):
    """This feed returns the results of a search feed. It lacks a second
    argument in the method b/c it gets its search query from a GET request."""
    feed_type = Atom1Feed

    # get the query info from the URL
    def get_object(self, request, get_string):
        return request

    title = "CourtListener.com custom search feed"

    def link(self, obj):
        return '/feed/search/?' + search_utils.make_get_string(obj)

    author_name = "CourtListener.com"
    author_email = "feeds@courtlistener.com"

    def items(self, obj):
        '''Do a Solr query here. Return the first 20 results'''
        search_form = SearchForm(obj.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
            main_params = search_utils.build_main_query(cd, highlight=False)
            main_params.update({'sort': 'dateFiled desc'})
            main_params['rows'] = '20'
            main_params['start'] = '0'
            results_si = conn.raw_query(**main_params).execute()
            return results_si
        else:
            return None

    def item_link(self, item):
        return item['absolute_url']

    def item_author_name(self, item):
        return item['court']

    def item_pubdate(self, item):
        import datetime
        return datetime.datetime.combine(item['dateFiled'], datetime.time())

    def item_title(self, item):
        return item['caseName']

    description_template = 'feeds/solr_desc_template.html'


class court_feed(Feed):
    """This feed returns the cases for a court, and accepts courts of the value:
    ca1, ca2..."""
    feed_type = Atom1Feed

    # get the court info from the URL
    def get_object(self, request, court):
        return get_object_or_404(Court, courtUUID=court)

    def title(self, obj):
        return "CourtListener.com: All opinions for the " + obj.full_name

    def link(self, obj):
        return '/feed/court/' + obj.courtUUID + '/'

    author_name = "CourtListener.com"
    author_email = "feeds@courtlistener.com"

    def items(self, obj):
        return Document.objects.filter(court=obj.courtUUID).order_by("-dateFiled")[:20]

    item_author_name = "CourtListener.com"

    def item_author_link(self, item):
        return item.court.URL

    def item_pubdate(self, item):
        import datetime
        return datetime.datetime.combine(item.dateFiled, datetime.time())

    def item_categories(self, item):
        cat = [item.get_documentType_display(), ]
        return cat

    description_template = 'feeds/template.html'
    title_template = 'feeds/title_template.html'


class all_courts_feed(Feed):
    """This feed returns the cases for all courts"""
    feed_type = Atom1Feed

    def title(self):
        return "CourtListener.com: All opinions (high volume)"

    def link(self):
        return '/feed/court/all/'

    author_name = "CourtListener.com"
    author_email = "feeds@courtlistener.com"

    def items(self, obj):
        return Document.objects.all().order_by("-dateFiled")[:20]

    item_author_name = "CourtListener.com"

    def item_author_link(self, item):
        return item.court.URL

    def item_pubdate(self, item):
        import datetime
        return datetime.datetime.combine(item.dateFiled, datetime.time())

    def item_categories(self, item):
        cat = [item.get_documentType_display(), ]
        return cat

    description_template = 'feeds/template.html'
    title_template = 'feeds/title_template.html'

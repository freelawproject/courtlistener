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

from django.contrib.syndication.views import Feed
from django.contrib.syndication.views import FeedDoesNotExist
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from django.utils import feedgenerator
from django.utils.feedgenerator import Atom1Feed

from alert.alertSystem.models import Court, Document
from alert.search.views import preparseQuery


class searchFeed(Feed):
    """This feed returns the results of a search feed. It lacks a second
    argument in the method b/c it gets its search query from a GET request."""
    feed_type = Atom1Feed

    # get the court info from the URL
    def get_object(self, request, query):
        try:
            query = request.GET['q']
        except:
            query = ''
        return query

    def title(self, obj):
        return "CourtListener.com results for the query: \"" + obj + "\""

    def link(self, obj):
        return '/feed/search/' + obj + '/'

    author_name = "CourtListener.com"
    author_email = "feeds@courtlistener.com"

    def items(self, obj):
        # Do a Sphinx query here. Return the first 20 results that aren't too
        # old (fixes issue 110)
        import datetime
        obj = preparseQuery(obj)
        queryset = Document.search.query(obj)
        results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
            .order_by('-dateFiled').filter(dateFiled__gt=datetime.date(1950, 1, 1))
        return results

    def item_author_name(self, item):
        return item.court

    def item_author_link(self, item):
        return item.court.courtURL

    def item_pubdate(self, item):
        import datetime
        return datetime.datetime.combine(item.dateFiled, datetime.time())

    def item_categories(self, item):
        cat = [item.get_documentType_display(),]
        return cat

    description_template = 'feeds/template.html'


class courtFeed(Feed):
    """This feed returns the cases for a court, and accepts courts of the value:
    ca1, ca2..."""
    feed_type = Atom1Feed

    # get the court info from the URL
    def get_object(self, request, court):
        return get_object_or_404(Court, courtUUID=court)

    def title(self, obj):
        return "CourtListener.com: All opinions for the " + obj.get_courtUUID_display()

    def link(self, obj):
        return '/feed/court/' + obj.courtUUID + '/'

    author_name = "CourtListener.com"
    author_email = "feeds@courtlistener.com"

    def items(self, obj):
        return Document.objects.filter(court = obj.courtUUID).order_by("-dateFiled")[:20]

    item_author_name = "CourtListener.com"

    def item_author_link(self, item):
        return item.court.courtURL

    def item_pubdate(self, item):
        import datetime
        return datetime.datetime.combine(item.dateFiled, datetime.time())

    def item_categories(self, item):
        cat = [item.get_documentType_display(),]
        return cat

    description_template = 'feeds/template.html'
    title_template = 'feeds/title_template.html'


class allCourtsFeed(Feed):
    """This feed returns the cases for all courts"""
    feed_type = Atom1Feed

    def title(self):
        return "CourtListener.com: All opinions for the circuit courts"

    def link(self):
        return '/feed/court/all/'

    author_name = "CourtListener.com"
    author_email = "feeds@courtlistener.com"

    def items(self, obj):
        return Document.objects.all().order_by("-dateFiled")[:20]

    item_author_name = "CourtListener.com"

    def item_author_link(self, item):
        return item.court.courtURL

    def item_pubdate(self, item):
        import datetime
        return datetime.datetime.combine(item.dateFiled, datetime.time())

    def item_categories(self, item):
        cat = [item.get_documentType_display(),]
        return cat

    description_template = 'feeds/template.html'
    title_template = 'feeds/title_template.html'

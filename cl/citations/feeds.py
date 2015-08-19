import datetime
from cl.lib.string_utils import trunc
from cl.search.models import Opinion
from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.utils.feedgenerator import Atom1Feed

class CitedByFeed(Feed):
    """Creates a feed of cases that cite a case, ordered by date filed."""
    feed_type = Atom1Feed

    # get the court info from the URL
    def get_object(self, request, doc_id):
        return get_object_or_404(Opinion, pk=doc_id)

    def title(self, obj):
        return "Cases Citing %s, Ordered by Filing Date" % \
               trunc(obj.cluster.case_name, 50)

    def link(self, obj):
        return '/feed/%s/cited-by/' % obj.pk

    author_name = "CourtListener.com"
    author_email = "feeds@courtlistener.com"

    def items(self, obj):
        """Return the latest 20 cases citing this one."""
        return obj.opinions_citing.all().order_by('-cluster__date_filed')[:20]

    def item_link(self, item):
        return item.cluster.get_absolute_url()

    def item_author_name(self, item):
        return item.cluster.docket.court

    def item_pubdate(self, item):
        return datetime.datetime.combine(item.cluster.date_filed, datetime.time())

    def item_title(self, item):
        return item

    def item_categories(self, item):
        return [item.cluster.precedential_status, ]

    description_template = 'feeds/template.html'

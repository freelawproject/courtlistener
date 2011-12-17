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

from alert.search.models import Court
from alert.search.models import Document
from alert import settings
from django.contrib.sitemaps import GenericSitemap
from django.contrib.sitemaps import FlatPageSitemap
from django.contrib.sites.models import Site
from django.core.paginator import EmptyPage, PageNotAnInteger
from django.core import urlresolvers
from django.http import HttpResponse, Http404
from django.template import loader
from django.utils.encoding import smart_str
from django.views.decorators.cache import never_cache

from string import count
import os

@never_cache
def index_copy(request, sitemaps):
    '''
    Copied from django.contrib.sitemaps.index. Had to, because it has the
    urlresolver hardcoded. Grr. Only difference is the urlresolvers.reverse
    line.
    '''
    current_site = Site.objects.get_current()
    sites = []
    protocol = request.is_secure() and 'https' or 'http'
    for section, site in sitemaps.items():
        if callable(site):
            pages = site().paginator.num_pages
        else:
            pages = site.paginator.num_pages
        sitemap_url = urlresolvers.reverse('alert.alerts.sitemap.cachedSitemap', kwargs={'section': section})
        sites.append('%s://%s%s' % (protocol, current_site.domain, sitemap_url))
        if pages > 1:
            for page in range(2, pages + 1):
                sites.append('%s://%s%s?p=%s' % (protocol, current_site.domain, sitemap_url, page))
    xml = loader.render_to_string('sitemap_index.xml', {'sitemaps': sites})
    return HttpResponse(xml, mimetype='application/xml')


@never_cache
def cached_sitemap(request, sitemaps, section=None):
    '''Copied from django.contrib.sitemaps.view, and modified to add a
    file-based cache.'''

    # creates two new lists
    maps, urls = [], []
    if section is not None:
        # if we are using an index page with section names
        if section not in sitemaps:
            # is the section name valid?
            raise Http404("No sitemap available for section: %r" % section)

        # it worked. Add the sitemap section name to the maps var.
        maps.append(sitemaps[section])
    else:
        # We're not using the index page with section names, simply get the
        # values of the sitemaps var.
        maps = sitemaps.values()

    page = request.GET.get("p", 1)

    # This is the custom part. Try to get a file with the page and section
    # name. If you can't, then build it.
    try:
        # is the sitemap on disk? If so, return it.
        filename = os.path.join(settings.MEDIA_ROOT, "sitemaps",
            section + "-p" + str(page) + ".xml")
        f = open(filename, 'r')
        xml = f.read()
        resp = HttpResponse(xml, mimetype='application/xml')
        f.close()
        return resp
    except IOError:
        # the sitemap is not cached to disk; make it, save it, return it
        for site in maps:
            try:
                if callable(site):
                    urls.extend(site().get_urls(page))
                else:
                    urls.extend(site.get_urls(page))
            except EmptyPage:
                raise Http404("Page %s empty" % page)
            except PageNotAnInteger:
                raise Http404("No page '%s'" % page)
        xml = smart_str(loader.render_to_string('sitemap.xml', {'urlset': urls}))

        # save the new sitemap to disk, but only if it's full-length
        if (count(xml, "<url>") == 250):
            # The sitemap is complete, cache it.
            filename = os.path.join(settings.MEDIA_ROOT, "sitemaps",
                section + "-p" + str(page) + ".xml")
            sitemap = open(filename, 'w')
            sitemap.write(xml)
            sitemap.close()

        return HttpResponse(xml, mimetype='application/xml')


class LimitedGenericSitemap(GenericSitemap):
    '''
    This class extends the GenericSitemap, so that we can limit it to only
    250 URLs.
    '''
    # if this is changed, the sitemap function (below) needs updating
    limit = 250

    def __init__(self, info_dict, priority=None, changefreq=None):
        # Extend the GenericSitemap __init__ method
        GenericSitemap.__init__(self, info_dict)
        self.priority = priority
        self.changefreq = changefreq
        # convert datetimes to dates, where necessary
        date_filed = info_dict.get('date_field', None)
        if type(date_filed).__name__ == 'datetime':
            date_filed = date_filed.date()
        self.date_field = date_filed


class MyFlatPageSitemap(FlatPageSitemap):
    '''Reprioritizes certain flatpages.

    Extends the FlatPageSitemap class so that specific priorities can be
    given to various pages; prioritizes the about page, deprioritizes
    the legal pages.'''
    def priority(self, item):
        if 'about' in str(item.get_absolute_url).lower():
            return 0.6
        elif 'coverage' in str(item.get_absolute_url).lower():
            return 0.7
        elif 'contribute' in str(item.get_absolute_url).lower():
            return 0.7
        elif 'dump' in str(item.get_absolute_url).lower():
            return 0.7
        else:
            return 0.2

    def changefreq(self, obj):
        return "monthly"


# from http://stackoverflow.com/questions/1392338/django-sitemap-index-example
# generates a variable, all_sitemaps, which can be handed to the sitemap index
# generator on the urls.py file. One sitemap per court + flatpages.
all_sitemaps = {}
pacer_codes = Court.objects.filter(in_use=True).values_list('courtUUID', flat=True)
for pacer_code in pacer_codes:
    info_dict = {
        'queryset'  : Document.objects.filter(court=pacer_code, blocked=False),
        'date_field': 'time_retrieved',
    }

    sitemap = LimitedGenericSitemap(info_dict, priority=0.5, changefreq="never")

    # dict key is provided as 'section' in sitemap index view
    all_sitemaps[pacer_code] = sitemap

# finally, we add the flatpages sitemap to the end
all_sitemaps["Flatfiles"] = MyFlatPageSitemap

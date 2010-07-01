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


#from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps import GenericSitemap
from django.contrib.sitemaps import FlatPageSitemap
from alert.alertSystem.models import Document
from alert.alertSystem.models import PACER_CODES



class LimitedGenericSitemap(GenericSitemap):
    # if this is changed, the sitemap function (below) needs updating
    limit = 1000

class MyFlatPageSitemap(FlatPageSitemap):
    # prioritizes the about page, deprioritizes the legal pages.
    def priority(self, item):
        if 'about' in str(item.get_absolute_url).lower():
            return 0.8
        elif 'coverage' in str(item.get_absolute_url).lower():
            return 0.7
        elif 'contribute' in str(item.get_absolute_url).lower():
            return 0.7
        else:
            return 0.2

    def changefreq(self, obj):
        return "monthly"

# from http://stackoverflow.com/questions/1392338/django-sitemap-index-example
# generates a variable, all_sitemaps, which can be handed to the sitemap index
# generator on the urls.py file. One sitemap per court + flatpages.
all_sitemaps = {}
for courtTuple in PACER_CODES:
    info_dict = {
        'queryset'  : Document.objects.filter(court=courtTuple[0]),
        'date_field': 'dateFiled',
    }

    sitemap = LimitedGenericSitemap(info_dict, priority=0.5, changefreq="never")

    # dict key is provided as 'section' in sitemap index view
    all_sitemaps[courtTuple[0]] = sitemap

# finally, we add the flatpages sitemap to the end
all_sitemaps["Flatfiles"] = MyFlatPageSitemap
  
"""
def sitemap(request, sitemaps, section=None):
    maps, urls = [], []
    if section is not None:
        if section not in sitemaps:
            raise Http404("No sitemap available for section: %r" % section)
        maps.append(sitemaps[section])
    else:
        maps = sitemaps.values()
    print maps
    
    return Null

    
    page = request.GET.get("p", 1)
    for site in maps:
        if 
            #check if it's in the cache
        else:
            # if it's not in the cache, make the page and return it
        
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
    return HttpResponse(xml, mimetype='application/xml')
    """





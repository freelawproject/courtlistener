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

# from http://stackoverflow.com/questions/1392338/django-sitemap-index-example
# generates a sitemap per court
all_sitemaps = {}
for courtTuple in PACER_CODES:
    info_dict = {
        'queryset'  : Document.objects.filter(court=courtTuple[0]),
        'date_field': 'dateFiled',
    }

    sitemap = GenericSitemap(info_dict, priority=0.5, changefreq="never")

    # dict key is provided as 'section' in sitemap index view
    all_sitemaps[courtTuple[0]] = sitemap


class MyFlatPageSitemap(FlatPageSitemap):
    # prioritizes the about page, deprioritizes the legal pages.
    def priority(self, item):
        if 'about' in str(item.get_absolute_url).lower():
            return 0.8
        elif 'contribute' in str(item.get_absolute_url).lower():
            return 0.7
        else:
            return 0.2

    def changefreq(self, obj):
        return "monthly"

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
from alert.alertSystem.models import Document
from alert.alertSystem.models import PACER_CODES


all_sitemaps = {}
for courtTuple in PACER_CODES:
    info_dict = {
        'queryset'  : Document.objects.filter(court=courtTuple[0]),
        'date_field': 'dateFiled',
    }

    sitemap = GenericSitemap(info_dict, priority=0.5, changefreq="never")

    # dict key is provided as 'section' in sitemap index view
    all_sitemaps[courtTuple[0]] = sitemap


"""
class DocumentSitemap(Sitemap):
    priority = 0.5
    limit = 5000

    def items(self):
        return Document.objects.filter('court'='ca4')

    def lastmod(self, obj):
        return obj.dateFiled

    # changefreq can be callable too
    def changefreq(self, obj):
        return "never"
"""

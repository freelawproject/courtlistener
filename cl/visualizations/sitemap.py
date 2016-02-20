from django.contrib.sitemaps import Sitemap
from cl.visualizations.models import SCOTUSMap


class VizSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5
    # limit = 1

    def items(self):
        return SCOTUSMap.objects.filter(deleted=False, published=True)

    def lastmod(self, obj):
        return obj.date_modified

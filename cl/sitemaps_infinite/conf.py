from collections import OrderedDict

from django.conf import settings

from cl.sitemaps_infinite.base_sitemap import InfinitePaginatorSitemap

# call sitemap file generation every 10 minutes
CELERY_TASK_REPETITION: int = getattr(
    settings, "SITEMAPS_TASK_REPEAT_SEC", 10 * 60
)

# The number of sitemap 'files' (pages) to cache per sitemap generation task call
FILES_PER_CALL: int = getattr(settings, "SITEMAPS_FILES_PER_CALL", 100)

# list of the sitemaps that should be generated in celery task
SITEMAPS: OrderedDict[str, InfinitePaginatorSitemap] = OrderedDict(
    getattr(settings, "SITEMAPS_GENERATED_OFFLINE", {})
)

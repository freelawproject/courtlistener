from collections import OrderedDict

from django.conf import settings

from cl.sitemaps_infinite.base_sitemap import InfinitePaginatorSitemap
from cl.sitemaps_infinite.utils import make_sitemaps_list

# call sitemap file generation, if CELERY_TASK_REPETITION > 0
CELERY_TASK_REPETITION: int = getattr(settings, "SITEMAPS_TASK_REPEAT_SEC", 0)

# The number of sitemap 'files' (pages) to cache per sitemap generation task call
FILES_PER_CALL: int = getattr(settings, "SITEMAPS_FILES_PER_CALL", 100)

# list of the sitemaps that should be generated in celery task
SITEMAPS: OrderedDict[str, InfinitePaginatorSitemap] = make_sitemaps_list(
    getattr(settings, "SITEMAPS_GENERATED_OFFLINE", {})
)

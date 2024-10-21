from cl.opinion_page.sitemap import DocketSitemap
from cl.search.models import SEARCH_TYPES

# call sitemap file generation every 10 minutes
SITEMAPS_TASK_REPEAT_SEC = 10 * 60

# The number of sitemap 'files' (pages) to cache per sitemap generation task call
SITEMAPS_FILES_PER_CALL = 100

# list of the sitemaps that should be generated in celery task
SITEMAPS_GENERATED_OFFLINE = {SEARCH_TYPES.RECAP: DocketSitemap}

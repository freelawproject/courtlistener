# The number of sitemap 'files' (pages) to cache per sitemap generation call
SITEMAPS_FILES_PER_CALL = 100

# list of the sitemaps that should be generated using the infinite pagination
# dict format:   {'section_name': 'sitemap_class', ...}
SITEMAPS_GENERATED_OFFLINE = {
    "r": "cl.opinion_page.sitemap.DocketSitemap" # cl.search.models.SEARCH_TYPES.RECAP
}

# @deprecated call sitemap file generation every 10 minutes via celery, set 0 to disable task (default)
SITEMAPS_TASK_REPEAT_SEC = 0
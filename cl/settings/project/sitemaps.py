# call sitemap file generation every 10 minutes, set 0 to disable task (default)
SITEMAPS_TASK_REPEAT_SEC = 0

# The number of sitemap 'files' (pages) to cache per sitemap generation task call
SITEMAPS_FILES_PER_CALL = 100

# list of the sitemaps that should be generated in celery task
SITEMAPS_GENERATED_OFFLINE = {
    "cl.search.models.SEARCH_TYPES.RECAP": "cl.opinion_page.sitemap.DocketSitemap"
}

import environ

env = environ.FileAwareEnv()

# The number of sitemap 'files' (pages) to cache per sitemap generation call
SITEMAPS_FILES_PER_CALL = env.int("SITEMAPS_FILES_PER_CALL", default=10)

# @deprecated call sitemap file generation every SITEMAPS_TASK_REPEAT_SEC seconds via celery, set 0 to disable task (default)
SITEMAPS_TASK_REPEAT_SEC = env.int("SITEMAPS_TASK_REPEAT_SEC", default=0)

import environ

env = environ.FileAwareEnv()

# The number of sitemap 'files' (pages) to cache per sitemap generation call
SITEMAPS_FILES_PER_CALL = env.int("SITEMAPS_FILES_PER_CALL", default=10)

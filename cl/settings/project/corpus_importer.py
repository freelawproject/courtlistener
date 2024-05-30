import environ

env = environ.FileAwareEnv()
IQUERY_SCRAPER_SHORT_WAIT = env.int("IQUERY_SHORT_WAIT", default=1)
IQUERY_SCRAPER_LONG_WAIT = env.int("IQUERY_SCRAPER_LONG_WAIT", default=60)
IQUERY_PROBE_THRESHOLD = env.int("IQUERY_PROBE_THRESHOLD", default=10)

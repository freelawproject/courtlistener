import environ

env = environ.FileAwareEnv()
MAX_CITATIONS_PER_REQUEST = env.int("MAX_CITATIONS_PER_REQUEST", default=250)

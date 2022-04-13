import environ

env = environ.FileAwareEnv()


REDIS_HOST = env("REDIS_HOST", default="cl-redis")
REDIS_PORT = 6379

# Redis is configured with 16 databases out of the box. This keeps them neatly
# mapped.
REDIS_DATABASES = {
    "CELERY": 0,
    "CACHE": 1,
    "STATS": 2,
    "ALERTS": 3,
}

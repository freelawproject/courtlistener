import environ
from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

env = environ.FileAwareEnv()


REDIS_HOST = env("REDIS_HOST", default="cl-redis")
REDIS_PORT = 6379
REDIS_MAX_RETRIES = env("REDIS_MAX_RETRIES", default=3)
REDIS_MAX_DELAY_IN_SECONDS = env("REDIS_MAX_DELAY_IN_SECONDS", default=4)
REDIS_BACKOFF_BASE = env("REDIS_BACKOFF_BASE", default=0.5)
REDIS_HEALTH_CHECK_INTERVAL = env("REDIS_HEALTH_CHECK_INTERVAL", default=15)

# Redis is configured with 16 databases out of the box. This keeps them neatly
# mapped.
REDIS_DATABASES = {
    "CELERY": 0,
    "CACHE": 1,
    "STATS": 2,
    "ALERTS": 3,
}
# Run 3 retries with exponential backoff strategy
retry = Retry(
    ExponentialBackoff(
        cap=REDIS_MAX_DELAY_IN_SECONDS, base=REDIS_BACKOFF_BASE
    ),
    REDIS_MAX_RETRIES,
)
# Redis clients with retries on custom errors
REDIS_CLIENTS = {
    f"{name}-{decode}": Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=db,  # type: ignore
        decode_responses=decode,
        retry=retry,
        retry_on_timeout=True,
        health_check_interval=REDIS_HEALTH_CHECK_INTERVAL,
    )
    for decode in [True, False]
    for name, db in REDIS_DATABASES.items()
}

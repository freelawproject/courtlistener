import environ
from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError
from redis.retry import Retry

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
# Run 3 retries with exponential backoff strategy
retry = Retry(ExponentialBackoff(cap=8, base=2), 3)
# Redis clients with retries on custom errors
REDIS_CLIENTS = {
    f"{name}-{decode}": Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=db,  # type: ignore
        decode_responses=decode,
        retry=retry,
        retry_on_error=[ConnectionError, TimeoutError],
        health_check_interval=15,
    )
    for decode in [True, False]
    for name, db in REDIS_DATABASES.items()
}

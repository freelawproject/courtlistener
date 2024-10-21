import environ

from .redis import REDIS_DATABASES, REDIS_HOST, REDIS_PORT

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)
CELERY_ETL_TASK_QUEUE = env("CELERY_ETL_TASK_QUEUE", default="celery")
CELERY_IQUERY_QUEUE = env("CELERY_IQUERY_QUEUE", default="celery")

# This can be useful in a dev environment:
# .virtualenvs/courtlistener/bin/celery worker -n w1 --app=cl  --loglevel=INFO
if DEVELOPMENT:
    # In a development machine, these setting make sense
    CELERY_WORKER_CONCURRENCY = 2
    # This makes the tasks run outside the async worker and is needed for tests
    # to pass
    CELERY_TASK_ALWAYS_EAGER = True
else:
    # Celery settings for production sites
    CELERY_WORKER_CONCURRENCY = 20
    CELERY_BROKER_POOL_LIMIT = 30
    CELERY_RESULT_EXPIRES = 60 * 60
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        # This is the length of time a task will wait to be acknowledged by a
        # worker. This value *must* be greater than the largest ETA/countdown
        # that a task may be assigned with, or else it will be run over and
        # over in a loop. Our countdowns never tend to exceed one hour.
        "visibility_timeout": (60 * 60 * 6),  # six hours
    }

CELERY_BROKER_URL = (
    f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DATABASES['CELERY']}"
)
CELERY_RESULT_BACKEND = (
    f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DATABASES['CELERY']}"
)

# Rate limits aren't ever used, so disable them across the board for better
# performance
CELERY_WORKER_DISABLE_RATE_LIMITS = True
# We could pass around JSON, but it's *much* easier to pass around Python
# objects that support things like dates. Let's do that, shall we?
CELERY_RESULT_SERIALIZER = "pickle"
CELERY_TASK_SERIALIZER = "pickle"
CELERY_ACCEPT_CONTENT = {"json", "pickle"}

from django.conf.urls import url

from cl.stats.views import celery_fail, redis_writes, sentry_fail

urlpatterns = [
    url(
        r"^monitoring/redis-writes/$", redis_writes, name="check_redis_writes"
    ),
    url(r"sentry/error/$", sentry_fail, name="sentry_fail"),
    url(r"sentry/celery-fail/$", celery_fail, name="celery_fail"),
]

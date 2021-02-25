from django.urls import path

from cl.stats.views import celery_fail, redis_writes, sentry_fail

urlpatterns = [
    path("monitoring/redis-writes/", redis_writes, name="check_redis_writes"),
    path("sentry/error/", sentry_fail, name="sentry_fail"),
    path("sentry/celery-fail/", celery_fail, name="celery_fail"),
]

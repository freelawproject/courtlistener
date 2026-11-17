"""Views for monitoring and checking the health of services."""

from http import HTTPStatus
from typing import NoReturn

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from cl.celery_init import fail_task
from cl.lib.celery_utils import get_queue_length
from cl.lib.redis_utils import get_redis_interface
from cl.stats.utils import (
    check_elasticsearch,
    check_postgresql,
    check_redis,
    get_replication_statuses,
)


async def heartbeat(request: HttpRequest) -> HttpResponse:
    """Respond with OK."""
    return HttpResponse("OK", content_type="text/plain")


def health_check(request: HttpRequest) -> JsonResponse:
    """Check if we can connect to various services."""
    is_redis_up = check_redis()
    is_postgresql_up = check_postgresql()

    status = HTTPStatus.OK
    if not all([is_redis_up, is_postgresql_up]):
        status = HTTPStatus.INTERNAL_SERVER_ERROR

    return JsonResponse(
        {"is_postgresql_up": is_postgresql_up, "is_redis_up": is_redis_up},
        status=status,
    )


def replication_status(request: HttpRequest) -> HttpResponse:
    """Render the status of each database's replication slots."""
    statuses = get_replication_statuses()
    return render(
        request,
        "replication_status.html",
        {"private": True, "statuses": statuses},
    )


def elasticsearch_status(request: HttpRequest) -> JsonResponse:
    """Checks the health of the Elasticsearch cluster."""
    if settings.ELASTICSEARCH_DISABLED:
        return JsonResponse(
            {"is_elastic_up": True, "elasticsearch_disabled": True},
            status=HTTPStatus.OK,
        )
    is_elastic_up = check_elasticsearch()
    return JsonResponse(
        {
            "is_elastic_up": is_elastic_up,
            "elasticsearch_disabled": False,
        },
        status=(
            HTTPStatus.OK
            if is_elastic_up
            else HTTPStatus.INTERNAL_SERVER_ERROR
        ),
    )


def redis_writes(request: HttpRequest) -> HttpResponse:
    """Just return 200 OK if we can write to redis. Else return 500 Error."""
    r = get_redis_interface("STATS")

    # Increment a counter. If it's "high" reset it. No need to do fancy try/
    # except work here to log or display the error. If there's an error, it'll
    # send a log we can review.
    key = "monitoring:redis-writes"
    v = r.incr(key)
    if v > 100:
        r.set(key, 0)

    return HttpResponse("Successful Redis write.", content_type="text/plain")


def sentry_fail(request: HttpRequest) -> NoReturn:
    """Raise an error on purpose to test Sentry."""
    raise ZeroDivisionError("Intentional error for Sentry")


def celery_fail(request: HttpRequest) -> HttpResponse:
    """Queue a task that fails on purpose to test Celery error reporting."""
    fail_task.delay()
    return HttpResponse("Successfully failed Celery.")


def celery_queue_lengths(request: HttpRequest) -> HttpResponse:
    """Respond with the length of each Celery queue as JSON."""
    queue_lengths = {}
    for q in settings.CELERY_QUEUES:
        queue_lengths[q] = get_queue_length(q)

    return JsonResponse(queue_lengths)

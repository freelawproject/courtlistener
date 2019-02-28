import redis
from django.conf import settings
from django.http import HttpResponse


def redis_writes(request):
    """Just return 200 OK if we can write to redis. Else return 500 Error."""
    r = redis.StrictRedis(host=settings.REDIS_HOST,
                          port=settings.REDIS_PORT,
                          db=settings.REDIS_DATABASES['STATS'])

    # Increment a counter. If it's "high" reset it. No need to do fancy try/
    # except work here to log or display the error. If there's an error, it'll
    # send a log we can review.
    key = 'monitoring:redis-writes'
    v = r.incr(key)
    if v > 100:
        r.set(key, 0)

    return HttpResponse("Successful Redis write.")


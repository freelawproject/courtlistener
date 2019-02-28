from django.conf.urls import url

from cl.stats.views import redis_writes

urlpatterns = [
    url(
        r'^monitoring/redis-writes/$',
        redis_writes,
        name='check_redis_writes',
    ),
]

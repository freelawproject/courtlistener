import redis
from django.conf import settings


def make_redis_interface(db_name: str) -> redis.Redis:
    """Create a redis connection object

    :param db_name: The name of the database to use, as defined in our settings
    :return Redis interface using django settings
    """
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DATABASES[db_name],
        decode_responses=True,
    )

import redis
from django.conf import settings


def make_redis_interface(
    db_name: str,
    decode_responses: bool = True,
) -> redis.Redis:
    """Create a redis connection object

    :param db_name: The name of the database to use, as defined in our settings
    :param decode_responses: Whether to decode responses with utf-8. If you're
    putting binary data (like a picked object) into redis, don't try to decode
    it.
    :return Redis interface using django settings
    """
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DATABASES[db_name],
        decode_responses=decode_responses,
    )

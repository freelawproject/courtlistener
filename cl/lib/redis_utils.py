import time
import uuid
from typing import Union, cast

from django.conf import settings
from redis import Redis
from redis.exceptions import WatchError


def make_redis_interface(
    db_name: str,
    decode_responses: bool = True,
) -> Redis:
    """Create a redis connection object

    :param db_name: The name of the database to use, as defined in our settings
    :param decode_responses: Whether to decode responses with utf-8. If you're
    putting binary data (like a picked object) into redis, don't try to decode
    it.
    :return Redis interface using django settings
    """
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=cast(int, settings.REDIS_DATABASES[db_name]),  # type: ignore
        decode_responses=decode_responses,
    )


def create_redis_semaphore(r: Union[str, Redis], key: str, ttl: int) -> bool:
    """Use a redis key to create a semaphore with a specified TTL

    Note that this function has a very small race condition between when it
    checks for the key, discovers it doesn't exist, and then creates it. This
    race condition is unfortunate. It can be fixed in one of two ways. A Lua
    script could be set up in the Redis server as described here:

      https://stackoverflow.com/a/36645586/64911

    Or Redis can be upgraded to a version where the SET command has a KEEPTTL
    parameter. Using that, you can set the value while keeping the TTL it might
    already have. In #1675 we learned that the obvious way of doing this, using
    getset, deletes the TTL from a key, making that approach untenable. So,
    instead of using that approach, or using a Lua script, we just accept the
    possibility of a race condition.

    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to make_redis_interface.
    :param key: The key to create
    :param ttl: How long the key should live
    :return: True if the key was created else False
    """
    if isinstance(r, str):
        r = make_redis_interface(r)

    currently_enqueued = bool(r.get(key))
    if currently_enqueued:
        # We've got the semaphore already
        return False

    # We don't have a key for this yet. Set a new expiring key. Normally, the
    # semaphores created by this function would be manually cleaned up by your
    # code, but if you fail to do so, the expiration gives a safety so that the
    # semaphore *will* eventually go away even if our task, server, whatever
    # crashes.
    # Redis doesn't do bools anymore, so use 1 as True.
    r.set(key, 1, ex=ttl)
    return True


def delete_redis_semaphore(r: Union[str, Redis], key: str) -> None:
    """Delete a redis key

    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to make_redis_interface.
    :param key: The key to delete
    :return: None
    """
    if isinstance(r, str):
        r = make_redis_interface(r)
    r.delete(key)


def acquire_lock(
    lock_name: str, ttl: int, acquire_timeout: int = 10
) -> str | bool:
    """Redis lock implementation with acquire time out and unique identifier in
     order to avoid conflicts when releasing the lock

    This implementation is based on:
        https://redis.com/ebook/part-2-core-concepts/chapter-6-application-components-in-redis/6-2-distributed-locking/6-2-3-building-a-lock-in-redis/

    With small changes like adding a TTL in order to avoid a deadlock in case
    of a redis failure.

    :param lock_name: The lock redis key
    :param ttl: The redis TTL expiration
    :param acquire_timeout: The timeout to until giving up to acquire the lock
    """

    redis_db = make_redis_interface("CACHE")
    identifier = str(uuid.uuid4())
    end = time.time() + acquire_timeout
    while time.time() < end:
        if redis_db.set(lock_name, identifier, nx=True, ex=ttl):
            return identifier
        time.sleep
    return False


def release_lock(lock_name: str, identifier: str) -> bool:
    """Releasing the acquire_lock redis lock

    :param lock_name: The lock redis key
    :param identifier: The lock unique identifier
    """

    redis_db = make_redis_interface("CACHE")
    pipe = redis_db.pipeline(True)
    while True:
        try:
            pipe.watch(lock_name)
            if pipe.get(lock_name) == identifier:
                pipe.multi()
                pipe.delete(lock_name)
                pipe.execute()
                return True
            pipe.unwatch()
            break
        except WatchError:
            pass
    return False

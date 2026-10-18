import time
import uuid

from django.conf import settings
from redis import Redis


def get_redis_interface(
    db_name: str,
    decode_responses: bool = True,
) -> Redis:
    """Pick an existing redis connection from the global object.

    :param db_name: The name of the database to use, as defined in our settings
    :param decode_responses: Whether to decode responses with utf-8. If you're
    putting binary data (like a picked object) into redis, don't try to decode
    it.
    :return Redis interface using django settings
    """
    return settings.REDIS_CLIENTS[f"{db_name}-{decode_responses}"]


def create_redis_semaphore(r: str | Redis, key: str, ttl: int) -> bool:
    """Use a redis key to create a semaphore with a specified TTL

    The key is created atomically with SET NX, so if several processes race
    to create the same semaphore, exactly one of them gets True.

    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to get_redis_interface.
    :param key: The key to create
    :param ttl: How long the key should live in seconds.
    :return: True if the key was created else False
    """
    if isinstance(r, str):
        r = get_redis_interface(r)

    # Normally, the semaphores created by this function would be manually
    # cleaned up by your code, but if you fail to do so, the expiration gives a
    # safety so that the semaphore *will* eventually go away even if our task,
    # server, whatever crashes. Redis doesn't do bools anymore, so use 1 as
    # True.
    return bool(r.set(key, 1, ex=ttl, nx=True))


def delete_redis_semaphore(r: str | Redis, key: str) -> None:
    """Delete a redis key

    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to get_redis_interface.
    :param key: The key to delete
    :return: None
    """
    if isinstance(r, str):
        r = get_redis_interface(r)
    r.delete(key)


def make_update_pacer_case_id_key(court_id: str) -> str:
    return f"update.pacer_case_id:{court_id}"


def acquire_redis_lock(r: Redis, key: str, ttl: int) -> str:
    """Acquires a lock in Redis.

    This method attempts to acquire a lock with the given key and TTL in Redis.
    If the lock is already in use by another process, it retries until the
    lock is acquired.

    :param r: The Redis DB to connect to as a connection interface.
    :param key: The key for the lock in Redis.
    :param ttl: Time-to-live for the lock in milliseconds.
    :return: A unique identifier for the lock.
    """

    identifier = str(uuid.uuid4())
    while True:
        if r.set(key, identifier, nx=True, px=ttl):
            return identifier
        time.sleep(0.1)


def release_redis_lock(r: Redis, key: str, identifier: str) -> int:
    """Releases an atomic lock in Redis.

    This method releases the lock with the given key and identifier in Redis.
    It uses a Lua script to ensure the lock is released atomically if the
    identifier matches the current lock value.
    This prevents other processes from mistakenly releasing the lock.

    :param r: The Redis DB to connect to as a connection interface.
    :param key: The key for the lock in Redis.
    :param identifier: The unique identifier for the lock.
    :return: None
    """
    # Lua script to release lock
    lua_script = """
    local lock_key = KEYS[1]
    local lock_value = ARGV[1]

    if redis.call("GET", lock_key) == lock_value then
        return redis.call("DEL", lock_key)
    else
        return 0
    end
    """
    return r.eval(lua_script, 1, key, identifier)


def hset_if_lock_held(
    r: Redis,
    lock_key: str,
    identifier: str,
    writes: list[tuple[str, str, str | int]],
) -> bool:
    """Atomically apply hash writes only if we still hold a lock.

    Use this for the writes made under a lock from acquire_redis_lock. The
    lock's TTL can expire while its holder is still working, letting another
    process acquire it. Writing through this function fences out the stale
    holder so it can't overwrite newer values. Either all the writes are
    applied or none are.

    :param r: The Redis DB to connect to as a connection interface.
    :param lock_key: The key of the lock in Redis.
    :param identifier: The identifier returned by acquire_redis_lock.
    :param writes: A list of (hash name, field, value) tuples to HSET.
    :return: True if the lock was held and the writes were applied, else
    False.
    """
    # KEYS[i] for i >= 2 is a hash name, and its field and value are in
    # ARGV[2i - 2] and ARGV[2i - 1].
    lua_script = """
    if redis.call("GET", KEYS[1]) ~= ARGV[1] then
        return 0
    end
    for i = 2, #KEYS do
        redis.call("HSET", KEYS[i], ARGV[2 * i - 2], ARGV[2 * i - 1])
    end
    return 1
    """
    keys = [lock_key] + [name for name, _, _ in writes]
    args = [identifier] + [
        arg for _, field, value in writes for arg in (field, value)
    ]
    return bool(r.eval(lua_script, len(keys), *keys, *args))

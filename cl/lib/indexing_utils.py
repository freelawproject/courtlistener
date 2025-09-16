from collections.abc import Mapping
from datetime import datetime

from cl.lib.redis_utils import get_redis_interface


def log_last_document_indexed(
    document_pk: int, log_key: str
) -> Mapping[str | bytes, int | str]:
    """Log the last document_id indexed in ES.

    :param document_pk: The last document_id processed.
    :param log_key: The log key to use in redis.
    :return: The data logged to redis.
    """

    r = get_redis_interface("CACHE")
    pipe = r.pipeline()
    pipe.hgetall(log_key)
    log_info: Mapping[str | bytes, int | str] = {
        "last_document_id": document_pk,
        "date_time": datetime.now().isoformat(),
    }
    pipe.hset(log_key, mapping=log_info)
    pipe.expire(log_key, 60 * 60 * 24 * 28)  # 4 weeks
    pipe.execute()

    return log_info


def get_last_parent_document_id_processed(log_key: str) -> int:
    """Get the last document ID indexed in ES.
    :return: The last document ID indexed.
    """
    r = get_redis_interface("CACHE")
    stored_values = r.hgetall(log_key)
    last_document_id = int(stored_values.get("last_document_id", 0))

    return last_document_id

import functools
import inspect
import random
import time
from typing import Any, Callable, Final, List, Tuple

from celery import Task

from cl.lib.command_utils import logger
from cl.lib.decorators import retry
from cl.lib.ratelimiter import parse_rate
from cl.lib.redis_utils import make_redis_interface

PRIORITY_SEP: str = "\x06\x16"
DEFAULT_PRIORITY_STEPS: List[int] = [0, 3, 6, 9]


def clear_queue(queue_name: str):
    """Empty out a queue, nuking the tasks in it."""
    priority_names = [
        make_queue_name_for_pri(queue_name, pri)
        for pri in DEFAULT_PRIORITY_STEPS
    ]
    r = make_redis_interface("CELERY")
    return sum([r.delete(x) for x in priority_names])


def make_queue_name_for_pri(queue: str, pri: int) -> str:
    """Make a queue name for redis

    Celery uses PRIORITY_SEP to separate different priorities of tasks into
    different queues in Redis. Each queue-priority combination becomes a key in
    redis with names like:

     - batch1\x06\x163 <-- P3 queue named batch1

    There's more information about this in Github, but it doesn't look like it
    will change any time soon:

      - https://github.com/celery/kombu/issues/422

    In that ticket the code below, from the Flower project, is referenced:

      - https://github.com/mher/flower/blob/master/flower/utils/broker.py#L135

    :param queue: The name of the queue to make a name for.
    :param pri: The priority to make a name with.
    :return: A name for the queue-priority pair.
    """
    if pri not in DEFAULT_PRIORITY_STEPS:
        raise ValueError("Priority not in priority steps")
    return "{0}{1}{2}".format(
        *((queue, PRIORITY_SEP, pri) if pri else (queue, "", ""))
    )


def get_queue_length(queue_name: str = "celery") -> int:
    """Get the number of tasks in a celery queue.

    :param queue_name: The name of the queue you want to inspect.
    :return: the number of items in the queue.
    """
    priority_names = [
        make_queue_name_for_pri(queue_name, pri)
        for pri in DEFAULT_PRIORITY_STEPS
    ]
    r = make_redis_interface("CELERY")
    return sum([r.llen(x) for x in priority_names])


class CeleryThrottle(object):
    """A class for throttling celery."""

    def __init__(
        self,
        poll_interval: float = 3.0,
        min_items: int = 50,
        queue_name: str = "celery",
    ) -> None:
        """Create a throttle to prevent celery runaways.

        :param poll_interval: How long to wait between polling the queue
        length in seconds, when you know it's greater than the min length.
        :param min_items: Generally keep the queue longer than this, and
        always shorter than 2× this value.
        """
        # All these variables are Final, i.e., they're consts. The only
        # instance variable that changes is the shortage variable below.
        self.min: Final = min_items
        self.max: Final = min_items * 2
        self.poll_interval: Final = poll_interval
        self.queue_name: Final = queue_name

        # `shortage` stores the number of items that the queue is short by, as
        # compared to `self.max`. At init, the queue is empty, so it's short by
        # the full amount. Fill it up.
        self.shortage = self.max

    def maybe_wait(self) -> None:
        """Make the user wait until the queue is short enough"""
        self.shortage -= 1
        if self.shortage > 0:
            # No need to sleep. Add items to the queue.
            return

        # No shortage we know of. Measure the queue to see if it's below
        # self.min. If so, we have a shortage that we should rectify.
        while True:
            queue_length = get_queue_length(self.queue_name)
            if queue_length > self.min:
                # The queue is still pretty full. Let it process a bit.
                time.sleep(self.poll_interval)
            else:
                # Refill the queue. As Michelle Obama says, when it goes low,
                # we go high.
                self.shortage = self.max - queue_length
                break


def throttle_task(
    rate: str,
    jitter: Tuple[float, float] = (1, 10),
    key: Any = None,
) -> Callable:
    """A decorator for throttling tasks to a given rate.

    :param rate: The maximum rate that you want your task to run. Takes the
    form of '1/m', or '10/2h' or similar.
    :param jitter: A tuple of the range of backoff times you want for throttled
    tasks. If the task is throttled, it will wait a random amount of time
    between these values before being tried again.
    :param key: An argument name whose value should be used as part of the
    throttle key in redis. This allows you to create per-argument throttles by
    simply passing the name of the argument you wish to key on.
    :return: The decorated function
    """

    def decorator_func(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Inspect the decorated function's parameters to get the task
            # itself and the value of the parameter referenced by key.
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            task = bound_args.arguments["self"]
            key_value = None
            if key:
                try:
                    key_value = bound_args.arguments[key]
                except KeyError:
                    raise KeyError(
                        f"Unknown parameter '{key}' in throttle_task "
                        f"decorator of function {task.name}. "
                        f"`key` parameter must match a parameter "
                        f"name from function signature: '{sig}'"
                    )
            proceed = is_rate_okay(task, rate, key=key_value)
            if not proceed:
                # Decrement the number of times the task has retried. If you
                # fail to do this, it gets auto-incremented, and you'll expend
                # retries during the backoff.
                task.request.retries = task.request.retries - 1
                countdown = random.uniform(*jitter)
                logger.info(
                    "Throttling task %s (%s) via decorator for %ss",
                    task.name,
                    task.request.id,
                    countdown,
                )
                return task.retry(countdown=countdown)
            else:
                # All set. Run the task.
                return func(*args, **kwargs)

        return wrapper

    return decorator_func


@retry(ConnectionError, tries=4, delay=0.25, backoff=1.5)
def is_rate_okay(task: Task, rate: str = "1/s", key=None) -> bool:
    """Keep a global throttle for tasks

    Can be used via the `throttle_task` decorator above.

    This implements the timestamp-based algorithm detailed here:

        https://www.figma.com/blog/an-alternative-approach-to-rate-limiting/

    Basically, you keep track of the number of requests and use the key
    expiration as a reset of the counter.

    So you have a rate of 5/m, and your first task comes in. You create a key:

        celery_throttle:task_name = 1
        celery_throttle:task_name.expires = 60

    Another task comes in a few seconds later:

        celery_throttle:task_name = 2
        Do not update the ttl, it now has 58s remaining

    And so forth, until:

        celery_throttle:task_name = 6
        (10s remaining)

    We're over the threshold. Re-queue the task for later. 10s later:

        Key expires b/c no more ttl.

    Another task comes in:

        celery_throttle:task_name = 1
        celery_throttle:task_name.expires = 60

    And so forth.

    :param task: The task that is being checked
    :param rate: How many times the task can be run during the time period.
    Something like, 1/s, 2/h or similar.
    :param key: If given, add this to the key placed in Redis for the item.
    Typically, this will correspond to the value of an argument passed to the
    throttled task.
    :return: Whether the task should be throttled or not.
    """
    key = f"celery_throttle:{task.name}{':' + str(key) if key else ''}"

    r = make_redis_interface("CACHE")

    num_tasks, duration = parse_rate(rate)

    # Check the count in redis
    count = r.get(key)
    if count is None:
        # No key. Set the value to 1 and set the ttl of the key.
        r.set(key, 1)
        r.expire(key, duration)
        return True
    else:
        # Key found. Check it.
        if int(count) <= num_tasks:
            # We're OK, run it.
            r.incr(key, 1)
            return True
        else:
            return False

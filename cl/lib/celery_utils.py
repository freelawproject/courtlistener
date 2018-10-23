# coding=utf-8
from collections import deque

import time

import redis
from django.conf import settings
from django.utils.timezone import now

PRIORITY_SEP = '\x06\x16'
DEFAULT_PRIORITY_STEPS = [0, 3, 6, 9]


def make_queue_name_for_pri(queue, pri):
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
        raise ValueError('Priority not in priority steps')
    return '{0}{1}{2}'.format(*((queue, PRIORITY_SEP, pri) if pri else
                                (queue, '', '')))


def get_queue_length(queue_name='celery'):
    """Get the number of tasks in a celery queue.
    
    :param queue_name: The name of the queue you want to inspect.
    :return: the number of items in the queue.
    """
    priority_names = [make_queue_name_for_pri(queue_name, pri) for pri in
                      DEFAULT_PRIORITY_STEPS]
    r = redis.StrictRedis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DATABASES['CELERY'],
    )
    return sum([r.llen(x) for x in priority_names])


class CeleryThrottle(object):
    """A class for throttling celery."""

    def __init__(self, min_items=100, min_wait=0, queue_name='celery'):
        """Create a throttle to prevent celery run aways.
        
        :param min_items: The minimum number of items that should be enqueued. 
        A maximum of 2× this number may be created. This minimum value is not 
        guaranteed and so a number slightly higher than your max concurrency 
        should be used. Note that this number includes all tasks unless you use
        a specific queue for your processing.
        :param min_wait: The minimum amount of time that should be waited every
        time `maybe_wait()` is called.
        """
        self.min = min_items
        self.max = self.min * 2
        self.min_wait = min_wait

        # Variables used to track the queue and wait-rate
        self.last_processed_count = 0
        self.count_to_do = self.max
        self.last_measurement = None
        self.first_run = True

        # Use a fixed-length queue to hold last N rates
        self.rates = deque(maxlen=15)
        self.avg_rate = self._calculate_avg()

        # For inspections
        self.queue_name = queue_name

    def _calculate_avg(self):
        return float(sum(self.rates)) / (len(self.rates) or 1)

    def _add_latest_rate(self):
        """Calculate the rate that the queue is processing items."""
        right_now = now()
        elapsed_seconds = (right_now - self.last_measurement).total_seconds()
        self.rates.append(self.last_processed_count / elapsed_seconds)
        self.last_measurement = right_now
        self.last_processed_count = 0
        self.avg_rate = self._calculate_avg()

    def maybe_wait(self):
        """Stall the calling function or let it proceed, depending on the queue.
        
        The idea here is to check the length of the queue as infrequently as 
        possible while keeping the number of items in the queue as closely 
        between self.min and self.max as possible.
        
        We do this by immediately enqueueing self.max items. After that, we 
        monitor the queue to determine how quickly it is processing items. Using 
        that rate we wait an appropriate amount of time or immediately press on.
        """
        self.last_processed_count += 1
        if self.count_to_do > 0:
            # Do not wait. Allow process to continue.
            if self.first_run:
                self.first_run = False
                self.last_measurement = now()
            self.count_to_do -= 1
            return

        self._add_latest_rate()
        task_count = get_queue_length(self.queue_name)
        if task_count > self.min:
            # Estimate how long the surplus will take to complete and wait that
            # long + 5% to ensure we're below self.min on next iteration.
            surplus_task_count = task_count - self.min
            wait_time = (surplus_task_count / self.avg_rate) * 1.05
            # Account for minimum wait time
            if self.min_wait:
                wait_time = max(wait_time, self.min_wait)
            time.sleep(wait_time)

            # Assume we're below self.min due to waiting; max out the queue.
            if task_count < self.max:
                self.count_to_do = self.max - self.min
            return

        elif task_count <= self.min:
            # Add more items.
            self.count_to_do = self.max - task_count
            if self.min_wait > 0:
                time.sleep(self.min_wait)
            return

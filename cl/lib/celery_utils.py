# coding=utf-8
from collections import deque

import time

import redis
from django.conf import settings
from django.utils.timezone import now


def get_queue_length(queue_name='celery'):
    """Get the number of tasks in a celery queue.
    
    :param queue_name: The name of the queue you want to inspect.
    :return: the number of items in the queue.
    """
    r = redis.StrictRedis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DATABASES['CELERY'],
    )
    return r.llen(queue_name)


class CeleryThrottle(object):
    """A class for throttling celery."""

    def __init__(self, min_items=100, queue_name='celery'):
        """Create a throttle to prevent celery run aways.
        
        :param min_items: The minimum number of items that should be enqueued. 
        A maximum of 2× this number may be created. This minimum value is not 
        guaranteed and so a number slightly higher than your max concurrency 
        should be used. Note that this number includes all tasks unless you use
        a specific queue for your processing.
        """
        self.min = min_items
        self.max = self.min * 2

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
            time.sleep(wait_time)

            # Assume we're below self.min due to waiting; max out the queue.
            if task_count < self.max:
                self.count_to_do = self.max - self.min
            return

        elif task_count <= self.min:
            # Add more items.
            self.count_to_do = self.max - task_count
            return

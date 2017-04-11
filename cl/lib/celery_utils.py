# coding=utf-8
from collections import deque

import time
from django.utils.timezone import now

from cl.celery import app


class CeleryThrottle(object):
    """A class for throttling celery."""

    def __init__(self, min_items, task_name=None):
        """Create a throttle to prevent celery run aways.
        
        :param min_items: The minimum number of items that should be enqueued by
        across all workers. A maximum of 2× this number may be created. This
        minimum value is not guaranteed and so a number slightly higher than
        your max concurrency should be used.
        :param task_name: If provided, the throttle will prevent a specific task
        from running away. Partial names are allowed. If not provided, the 
        throttle will stop your code until the entire queue has min_items in it.
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
        self.inspector = app.control.inspect()
        self.task_name = task_name

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

    def _get_worker_task_count(self):
        """Get the count of tasks currently executing across all workers."""
        # Make a flat list of tasks across all workers.
        tasks = [t for worker in self.inspector.active().values()
                 for t in worker]
        if self.task_name is not None:
            tasks = filter(lambda task: self.task_name in task['name'], tasks)
        return len(tasks)

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
        task_count = self._get_worker_task_count()
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

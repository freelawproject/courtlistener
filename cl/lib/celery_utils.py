# coding=utf-8
from Queue import Queue
from threading import Thread

from django.conf import settings


def blocking_queue(iterable, func, thread_count=settings.CELERYD_CONCURRENCY):
    """Create a blocking queue for celery tasks.

    This creates a queue so that long-running Celery tasks can be run without
    clogging the entire Celery queue. Unlike the Celery queue, this queue is
    finite in size, so it blocks if you try to add something to it when it is
    full.

    :param iterable: An iterable that will be pushed onto the queue and then
    popped off the queue. This will usually have something like a list of IDs
    to process.
    :param func: A function that starts a celery task and blocks until it is
    complete.
    :param thread_count: The number of threads you wish to use to run `func`. By
    default, this is equal to CELERYD_CONCURRENCY. Putting it higher is not
    expected to have any effect. Putting it lower will reduce Celery concurrency
    for the job.
    """
    queue = Queue(thread_count + 1)

    def wrapped_func(queue):
        # Wrap the normal python function in a while loop that pulls things off
        # the queue.
        while True:
            try:
                func(queue.get())
            finally:
                queue.task_done()

    # Fire up a bunch of threads to do processing, each loaded with a while
    # loop that's on the hunt for new items in the queue.
    for _ in range(thread_count):
        t = Thread(target=wrapped_func, args=(queue,))
        t.daemon = True
        t.start()

    # Iterate over the item IDs and add each to the queue for processing. (These
    # will get processed instantly, because there are already X threads waiting
    # for work.
    for i in iterable:
        queue.put(i)

    # The last item will be added to the queue before all items are processed.
    # ∴, join until all items are complete.
    try:
        queue.join()
    except KeyboardInterrupt:
        exit()

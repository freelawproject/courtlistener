from copy import deepcopy

from celery.canvas import subtask, group

from cl.celery import app


@app.task
def dmap(iterable, callback):
    """Map a callback over an iterator and return as a group

    This allows you to pipe an iterable of results into another task, running
    one instance of the task per item in the iterable.

    See: http://stackoverflow.com/a/13569873/64911
    Usage: process_list = (get_list.s(10) | dmap.s(process_item.s()))
    """
    callback = subtask(callback)
    return group(deepcopy(callback).clone([arg]) for arg in iterable)()

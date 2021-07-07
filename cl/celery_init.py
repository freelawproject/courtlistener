import os
import sys

from celery import Celery

from cl.lib.celery_utils import throttle_task

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cl.settings")

app = Celery("cl")

# Bump the recursion limit to 10× normal to account for really big chains. See:
# https://github.com/celery/celery/issues/1078
sys.setrecursionlimit(10000)

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
@throttle_task("2/4s")
def debug_task(self) -> None:
    print(f"Request: {self.request!r}")


@app.task(bind=True)
def fail_task(self) -> float:
    # Useful for things like sentry
    return 1 / 0

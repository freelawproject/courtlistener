# coding=utf-8
from __future__ import absolute_import
import os
import sys
from celery import Celery

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cl.settings')

app = Celery('cl')

# Bump the recursion limit to 10× normal to account for really big chains. See:
# https://github.com/celery/celery/issues/1078
sys.setrecursionlimit(10000)

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

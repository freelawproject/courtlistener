import os
import sys

# See https://modwsgi.readthedocs.org/en/latest/application-issues/index.html#non-blocking-module-imports
import _strptime

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'
os.environ["CELERY_LOADER"] = "django"

sys.path.append('/var/www/court-listener')
sys.path.append('/var/www/court-listener/alert')
import django.core.handlers.wsgi
application = django.core.handlers.wsgi.WSGIHandler()

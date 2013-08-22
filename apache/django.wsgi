import os
import sys

# See https://modwsgi.readthedocs.org/en/latest/application-issues/index.html#non-blocking-module-imports
import _strptime

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'
os.environ["CELERY_LOADER"] = "django"

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
sys.path.append('%s/alert' % INSTALL_ROOT)
import django.core.handlers.wsgi
application = django.core.handlers.wsgi.WSGIHandler()

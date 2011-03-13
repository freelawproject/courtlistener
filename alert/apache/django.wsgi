import os
import sys

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

sys.path.append('/var/www/court-listener')
import django.core.handlers.wsgi
application = django.core.handlers.wsgi.WSGIHandler()

import os
import sys

from django.core.wsgi import get_wsgi_application

os.environ["DJANGO_SETTINGS_MODULE"] = "cl.settings"

sys.path.append("/opt/courtlistener")
application = get_wsgi_application()

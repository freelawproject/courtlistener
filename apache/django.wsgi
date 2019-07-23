import os
import sys
from django.core.wsgi import get_wsgi_application

os.environ['DJANGO_SETTINGS_MODULE'] = 'cl.settings'

execfile('/etc/courtlistener')
sys.path.append('%s/cl' % INSTALL_ROOT)
application = get_wsgi_application()

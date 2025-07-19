# Copy this to local_private.py and uncomment the corresponding line in
# your .env.dev file.
from . import *


############
# Examples #
############

# To show embedded files from the public site.  Use this for data you have
# reproduced or cloned from the public API.

#AWS_S3_CUSTOM_DOMAIN = "storage.courtlistener.com"
#CSP_CONNECT_SRC += (f"https://{AWS_S3_CUSTOM_DOMAIN}/",)  # for embedded PDFs


# A troubleshooting step if the Django Debug Toolbar is not loading.  For
# example, the desktop version of Docker proxies all requests through an
# internal IP (Settings->Resources->Network->Docker subnet).  This doesn't get
# picked up by our INTERNAL_IPS logic.

#DEBUG_TOOLBAR_CONFIG = {
#	"SHOW_TOOLBAR_CALLBACK": lambda request: True,
#}

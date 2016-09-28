from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.cache import add_never_cache_headers
from rest_framework.status import HTTP_503_SERVICE_UNAVAILABLE


class MaintenanceModeMiddleware(object):
    """ Provides maintenance mode if requested in settings.

    This cribs heavily from:
      - https://github.com/fabiocaccamo/django-maintenance-mode

    But there are a few differences. First, we drop a lot of the functionality.
    For example, there's no distinction between staff and super users, there's
    no mechanism for enabling this by script or URL, etc.

    Second, we set this up so that it raises a MiddlewareNotUsed exception if
    maintenance mode is not enabled. Because this is in init instead of in the
    process_request method, it runs the logic once, when the code is
    initialized, instead of running it on every page request. This should make
    it (very slightly) faster.

    The third difference is that this provides is that it sets the maintenance
    mode page to never be cached.

    We also eschew using the code from Github to reduce our reliance on third-
    party code.
    """
    def __init__(self):
        super(MaintenanceModeMiddleware, self).__init__()
        if not settings.MAINTENANCE_MODE_ENABLED:
            raise MiddlewareNotUsed

    def process_request(self, request):
        if hasattr(request, 'user'):
            if settings.MAINTENANCE_MODE_ALLOW_STAFF and request.user.is_staff:
                return None

        for ip_address_re in settings.MAINTENANCE_MODE_ALLOWED_IPS:
            if ip_address_re.match(request.META['REMOTE_ADDR']):
                return None

        r = render_to_response(
             'maintenance.html',
             {'private': True},
             RequestContext(request),
             status=HTTP_503_SERVICE_UNAVAILABLE,
        )
        add_never_cache_headers(r)
        return r

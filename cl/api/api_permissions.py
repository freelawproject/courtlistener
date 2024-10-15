from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpRequest
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView

from cl.api.utils import get_logging_prefix
from cl.lib.redis_utils import get_redis_interface


class IsOwner(permissions.BasePermission):
    """Only allow changes to visualizations by its owner"""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user


class V3APIPermission(permissions.BasePermission):

    r = get_redis_interface("STATS")

    def is_new_v3_user(self, user: User) -> bool:
        """Check if the user is new for V3 by determining their presence in the
        V3 API stats.

        :param user: The User to check.
        :return: True if the user is new for V3, False otherwise.
        """
        api_prefix = get_logging_prefix("v3")
        set_key = f"{api_prefix}.user.counts"
        score = self.r.zscore(set_key, user.id)
        return score is None

    @staticmethod
    def is_v3_api_request(request: HttpRequest) -> bool:
        return getattr(request, "version", None) == "v3"

    def has_permission(self, request: HttpRequest, view: APIView) -> bool:
        """Check if the user has permission to access the V3 API.

        :param request: The HTTPRequest object.
        :param view: The APIview being accessed.
        :return: True if the user has permission to access V3, False if not.
        """

        if (
            not self.is_v3_api_request(request)
            or not settings.BLOCK_NEW_V3_USERS
        ):
            # Allow the request if it is not a V3 request
            return True

        user = request.user
        if not user.pk:
            # Block V3 for Anonymous users.
            raise PermissionDenied(
                "Anonymous users don't have permission to access V3 of the API. "
                "Please use V4 instead."
            )
        if user.is_authenticated and self.is_new_v3_user(user):
            raise PermissionDenied(
                "As a new user, you don't have permission to access V3 of the API. "
                "Please use V4 instead."
            )
        return True

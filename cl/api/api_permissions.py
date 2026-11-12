"""REST API permission classes."""

import random

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.views import APIView

from cl.lib.redis_utils import get_redis_interface


class IsOwner(permissions.BasePermission):
    """Only allow changes to visualizations by its owner."""

    def has_object_permission(self, request, view, obj):
        """Allow safe methods for anyone and other methods for the object's user."""
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user


class V3APIPermission(permissions.BasePermission):
    """Block anonymous and new users from the V3 API.

    Only applies when ``BLOCK_NEW_V3_USERS`` is set. Users are checked
    against Redis sets of known and blocked V3 users.
    """

    r = get_redis_interface("STATS")
    v3_blocked_message = (
        "As a new user, you don't have permission to access V3 of the API. "
        "Please use V4 instead."
    )
    v3_blocked_list_key = "v3-blocked-users-list"
    v3_users_list_key = "v3-users-list"

    def is_new_v3_user(self, user: User) -> bool:
        """Check if the user is new for V3 by determining their presence in the v3-users-list.

        Args:
            user: The User to check.

        Returns:
            True if the user is new for V3, False otherwise.
        """
        is_new_user = self.r.sismember(self.v3_users_list_key, user.id) != 1
        return is_new_user

    def is_user_v3_blocked(self, user: User) -> bool:
        """Check if the user is already blocked form V3 by determining their presence in the v3-blocked-users-list.

        Args:
            user: The User to check.

        Returns:
            True if the user is blocked for V3, False otherwise.
        """
        is_blocked_user = (
            self.r.sismember(self.v3_blocked_list_key, user.id) == 1
        )
        return is_blocked_user

    @staticmethod
    def is_v3_api_request(request: Request) -> bool:
        """Check if the request is for the V3 API."""
        return getattr(request, "version", None) == "v3"

    @staticmethod
    def check_request() -> bool:
        """Randomly select about one in 50 requests for checking."""
        # Check 1 in 50 requests.
        if random.randint(1, 50) == 1:
            return True
        return False

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if the user has permission to access the V3 API.

        Args:
            request: The HTTPRequest object.
            view: The APIview being accessed.

        Returns:
            True if the user has permission to access V3, False if not.
        """
        if (
            not self.is_v3_api_request(request)
            or not settings.BLOCK_NEW_V3_USERS  # type: ignore
        ):
            # Allow the request if it is not a V3 request
            return True

        user = request.user
        if isinstance(user, AnonymousUser):
            # Block V3 for all Anonymous users.
            raise PermissionDenied(
                "Anonymous users don't have permission to access the API. "
            )

        if self.is_user_v3_blocked(user):
            # Check if user has been blocked from V3.
            raise PermissionDenied(self.v3_blocked_message)

        if not self.check_request():
            return True

        if user.is_authenticated and self.is_new_v3_user(user):
            # This a new user. Block request and add it to v3-blocked-list
            self.r.sadd(self.v3_blocked_list_key, user.id)
            raise PermissionDenied(self.v3_blocked_message)
        return True

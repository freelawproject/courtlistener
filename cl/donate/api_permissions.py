from django.conf import settings
from rest_framework import exceptions, permissions


class AllowNeonWebhook(permissions.BasePermission):
    """
    Validates requests received from Neon by verifying the included signature
    against a configured secret token.
    """

    def has_permission(self, request, view):
        if settings.DEVELOPMENT:
            return True

        payload = request.data
        if not payload:
            raise exceptions.ParseError(
                detail="The request contains malformed data"
            )

        request_token = payload["customParameters"].get("webhook_token", None)
        if not request_token:
            raise exceptions.PermissionDenied("The token was not provided")

        if request_token != settings.NEON_AUTHORIZATION_TOKEN:
            raise exceptions.PermissionDenied("The provided token is invalid")

        return True

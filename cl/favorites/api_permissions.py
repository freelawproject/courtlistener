"""REST API permission classes for tags."""

from rest_framework import permissions


class IsTagOwner(permissions.BasePermission):
    """Only allow people to see the items in the m2m table if they have permission."""

    def has_object_permission(self, request, view, obj):
        """Allow safe methods for anyone and other methods for the tag's owner."""
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.tag.user == request.user

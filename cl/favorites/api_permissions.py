from rest_framework import permissions


class IsTagOwner(permissions.BasePermission):
    """Only allow people to see the items in the m2m table if they have
    permission
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.tag.user == request.user

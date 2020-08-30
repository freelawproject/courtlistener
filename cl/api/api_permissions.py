from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """Only allow changes to visualizations by its owner"""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user

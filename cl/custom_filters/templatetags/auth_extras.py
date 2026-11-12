"""Template filters for checking user permissions."""

from django import template

register = template.Library()


@register.filter(name="in_group")
def in_group(user, group_name):
    """Check if the user is in the named group or is a superuser."""
    if bool(user.groups.filter(name=group_name)) or user.is_superuser:
        return True
    return False

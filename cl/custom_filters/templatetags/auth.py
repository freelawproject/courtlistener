from django import template
from django.contrib.auth.models import User

register = template.Library()


@register.filter(name="in_group")
def in_group(user: User, group_name: str) -> bool:
    if bool(user.groups.filter(name=group_name)) or user.is_superuser:
        return True
    return False

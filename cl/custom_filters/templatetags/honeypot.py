from django import template
from django.conf import settings

from cl.custom_filters.decorators import HONEYPOT_FIELD_NAME

register = template.Library()


@register.inclusion_tag("includes/honeypot_field.html")
def render_honeypot_field() -> dict[str, str]:
    """Renders the honeypot field."""
    value = getattr(settings, "HONEYPOT_VALUE", "")
    if callable(value):
        value = value()
    return {"fieldname": HONEYPOT_FIELD_NAME, "value": value}

from django import template
from django.conf import settings

register = template.Library()

@register.inclusion_tag('includes/honeypot_field.html')
def render_honeypot_field(field_name=None):
    """
        Renders honeypot field named field_name (defaults to HONEYPOT_FIELD_NAME).
    """
    if not field_name:
        field_name = settings.HONEYPOT_FIELD_NAME
    value = getattr(settings, 'HONEYPOT_VALUE', '')
    if callable(value):
        value = value()
    return {'fieldname': field_name, 'value': value}

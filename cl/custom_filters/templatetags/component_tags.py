from django import template
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def require_script(context, script_path):
    """Registers a script to be loaded"""
    if "request" not in context:
        return ""

    request = context["request"]
    if not hasattr(request, "_required_scripts"):
        setattr(request, "_required_scripts", set())

    request._required_scripts.add(script_path)
    return ""


@register.simple_tag(takes_context=True)
def render_required_scripts(context):
    """Renders all required scripts"""
    if "request" not in context:
        return "NO REQUEST"

    request = context["request"]
    if not hasattr(request, "_required_scripts"):
        return ""

    if not request._required_scripts:
        return ""

    nonce = ""
    if hasattr(request, "csp_nonce"):
        nonce = f' nonce="{request.csp_nonce}"'

    script_tags = []
    for script_path in request._required_scripts:
        script_url = static(script_path)
        script_tags.append(
            f'<script type="text/javascript" src="{script_url}"{nonce}></script>'
        )

    return mark_safe("\n".join(script_tags))

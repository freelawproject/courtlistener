from django import template
from django.templatetags.static import static
from django.utils.html import format_html
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

    nonce = getattr(request, "csp_nonce", "")

    script_tags = []
    for script_path in request._required_scripts:
        script_url = static(script_path)
        if nonce:
            script_tags.append(
                format_html(
                    '<script type="text/javascript" src="{}" nonce="{}"></script>',
                    script_url,
                    nonce,
                )
            )
        else:
            script_tags.append(
                format_html(
                    '<script type="text/javascript" src="{}"></script>',
                    script_url,
                )
            )

    return mark_safe("\n".join(script_tags))

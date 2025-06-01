from django import template
from django.conf import settings
from django.template import TemplateSyntaxError
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


def _script_registry_for(request):
    """
    Gets or sets the script registry for this request.
    """
    if not hasattr(request, "_required_component_scripts"):
        setattr(request, "_required_component_scripts", dict())
    return request._required_component_scripts


def _coerce_defer(value, script_path):
    """
    Accepts the real booleans True/False or the strings 'true'/'false'.

    Raises:
        TemplateSyntaxError: any other value.
    """
    if value in {True, False}:
        return value

    val = str(value).lower()

    if val in {"true", "false"}:
        return val == "true"

    raise TemplateSyntaxError(
        f"Invalid defer flag {value!r} for script '{script_path}'. "
        "Use defer=True or defer=False."
    )


def _resolved_path(path_stub):
    """Append .js / .min.js when the provided path lacks an extension."""
    if path_stub.endswith(".js"):
        return path_stub
    suffix = ".js" if settings.DEBUG else ".min.js"
    return f"{path_stub}{suffix}"


@register.simple_tag(takes_context=True)
def require_script(context, script_path, **kwargs):
    """
    Register .js scripts required for a given template. To enable the use of minified files
    in production only, simply omit the extension in the script_path.

    Usage:
        {% load component_tags %}
        {% require_script 'js/alpine/components/tabs.js' %}
        {% require_script 'js/alpine/plugins/intersect@3.14.8' defer=True %}

    Notes:
        - Alpine components ('js/alpine/components/') should *NOT* be deferred.
        - Alpine plugins ('js/alpine/plugins/') *SHOULD* be deferred.
        - If `script_path` **already ends with ".js"**, it is used verbatim.
        - If `script_path` has **no extension**, we append ".js" when settings.DEBUG is True and ".min.js" when it's False

    Raises:
        TemplateSyntaxError:
            - If the same script is required twice with different defer flags.
            - If an invalid value is passed to the defer flag.
    """
    if "request" not in context:
        return ""

    script_path = _resolved_path(script_path)
    defer_flag = _coerce_defer(kwargs.get("defer", False), script_path)
    registry = _script_registry_for(context["request"])

    previous_defer_flag = registry.get(script_path)
    if previous_defer_flag is None:
        registry[script_path] = defer_flag
    elif previous_defer_flag != defer_flag:
        raise TemplateSyntaxError(
            f"Script '{script_path}' registered with defer={previous_defer_flag} "
            f"and defer={defer_flag}. Please resolve the conflict."
        )
    return ""


@register.simple_tag(takes_context=True)
def render_required_scripts(context):
    """
    Renders the required scripts for this request right before the Alpine script.
    """
    if "request" not in context:
        return ""

    registry = getattr(context["request"], "_required_component_scripts", None)
    if not registry:
        return ""

    nonce_attr = ""
    nonce = getattr(context["request"], "csp_nonce", "")
    if nonce:
        nonce_attr = f' nonce="{nonce}"'

    pieces = []
    for path, defer_flag in registry.items():
        attr_defer = " defer" if defer_flag else ""
        pieces.append(
            format_html(
                '<script type="text/javascript" src="{}"{}{}></script>',
                static(path),
                attr_defer,
                mark_safe(nonce_attr),
            )
        )
    return mark_safe("\n".join(pieces))

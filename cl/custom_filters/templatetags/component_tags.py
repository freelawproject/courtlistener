import logging
from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpRequest
from django.middleware.csp import get_nonce
from django.template import TemplateSyntaxError
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)

register = template.Library()


def _script_registry_for(request):
    """
    Gets or sets the script registry for this request.
    """
    if not hasattr(request, "_required_component_scripts"):
        setattr(request, "_required_component_scripts", dict())
    return request._required_component_scripts


def _extensionless_registry_for(request: HttpRequest) -> set[str]:
    """
    Gets or sets the registry of scripts required without an extension.
    """
    if not hasattr(request, "_extensionless_scripts"):
        setattr(request, "_extensionless_scripts", set())
    return request._extensionless_scripts


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


def _script_problems(path_stub: str) -> list[str]:
    """Problems with the files an extension-less stub resolves to.

    DEBUG loads the ``.js`` and production loads the ``.min.js``, so both
    have to be committed with content.
    """
    problems = []
    for suffix in (".js", ".min.js"):
        static_path = f"{path_stub}{suffix}"
        path = finders.find(static_path)
        if path is None:
            problems.append(f"{static_path} is missing")
        elif not Path(path).read_bytes().strip():
            problems.append(f"{static_path} is empty")
    return problems


def _warn_about_unusable_scripts(request: HttpRequest) -> None:
    """Logs one warning per problem with a registered stub's files.

    No-op outside DEBUG.
    """
    if not settings.DEBUG:
        return

    for path_stub in getattr(request, "_extensionless_scripts", ()):
        for problem in _script_problems(path_stub):
            logger.warning(
                f"require_script: {problem}. Requiring '{path_stub}' without "
                "an extension needs a .js for DEBUG and a .min.js for "
                "production — commit both, or require the script with its "
                "'.js' extension."
            )


@register.simple_tag(takes_context=True)
def require_script(context, script_path, **kwargs):
    """
    Register .js scripts required for a given template. To enable the use of minified files
    in production only, simply omit the extension in the script_path.

    Usage:
        {% load component_tags %}
        {% require_script 'js/alpine/components/tabs.js' %}
        {% require_script 'js/alpine/plugins/intersect' defer=True %}

    Notes:
        - Alpine components ('js/alpine/components/') should *NOT* be deferred.
        - Alpine plugins ('js/alpine/plugins/') *SHOULD* be deferred.
        - If `script_path` **already ends with ".js"**, it is used verbatim.
        - If `script_path` has **no extension**, we append ".js" when settings.DEBUG is True and ".min.js" when it's False
        - Omitting the extension requires both a committed ".js" and
          ".min.js". A missing or empty one warns during render under
          DEBUG, and fails the test suite.

    Raises:
        TemplateSyntaxError:
            - If the same script is required twice with different defer flags.
            - If an invalid value is passed to the defer flag.
    """
    if "request" not in context:
        return ""

    if not script_path.endswith(".js"):
        _extensionless_registry_for(context["request"]).add(script_path)

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

    _warn_about_unusable_scripts(context["request"])

    registry = getattr(context["request"], "_required_component_scripts", None)
    if not registry:
        return ""

    # Read the nonce off the request rather than the {{ csp_nonce }} context
    # variable, so this keeps working in a template rendered without the csp
    # context processor. get_nonce() is what that processor calls anyway.
    #
    # It hands back a lazy object that only generates the nonce once something
    # interpolates it, and that object is falsy until then, so the test below
    # has to be against None rather than truthiness. None itself means the CSP
    # middleware never ran.
    nonce = get_nonce(context["request"])
    nonce_attr = "" if nonce is None else f' nonce="{nonce}"'

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

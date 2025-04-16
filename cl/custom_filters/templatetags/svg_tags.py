from django import template
from django.conf import settings
from django.contrib.staticfiles.finders import find
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag()
def svg(name, css_class="", **kwargs):
    """
    Include an SVG file directly in the template.

    Usage:
    ```
    {% load svg_tags %}
    {% svg "icon-name" css_class="w-6 h-6 text-gray-500" %}
    ```

    Note HTML attributes are passed directly with minor adjustments:
    - Use "css_class" instead of "class", as "class" is reserved in python.
    - Use snake case instead of kebab, as template tags don't support kebab.
    - To include Alpine bindings, use "__" instead of ":" (e.g. `x_bind__class="w-full"`)

    These are all handled by the tag under the hood.
    """
    relative_path = f"svg/{name}.svg"
    absolute_path = find(relative_path)

    if not absolute_path:
        if settings.DEBUG:
            return f"SVG '{name}' not found at '{relative_path}'"
        return ""

    try:
        with open(absolute_path, "r") as file:
            svg_content = file.read()

        if css_class:
            if 'class="' in svg_content:
                svg_content = svg_content.replace(
                    'class="', f'class="{css_class} '
                )
            else:
                svg_content = svg_content.replace(
                    "<svg", f'<svg class="{css_class}"'
                )

        for key, value in kwargs.items():
            key = key.replace("__", ":")  # Convert double underscore to colons
            key = key.replace("_", "-")  # Convert snake_case to kebab-case
            svg_content = svg_content.replace("<svg", f'<svg {key}="{value}"')

        return mark_safe(svg_content)

    except FileNotFoundError:
        if settings.DEBUG:
            return f"SVG '{name}' file found but couldn't be opened at '{absolute_path}'"
        return ""

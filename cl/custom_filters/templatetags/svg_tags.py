"""Template tag for inlining SVG files."""

from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles.finders import find
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag()
def svg(name, **kwargs):
    """Include an SVG file directly in the template.

    Usage:
    ```
    {% load svg_tags %}
    {% svg "icon-name" class="w-6 h-6 text-gray-500" %}
    ```

    Note HTML attributes are passed directly with minor adjustments:

    - Use snake case instead of kebab, as template tags don't support kebab.
    - To include Alpine bindings, use "__" instead of ":" (e.g. `x_bind__class="w-full"`)
    - Passing class= here will inject it into every element that already has a class, so
      only use the class argument when no nested tags include their own class attributes,
      otherwise style the SVG’s parent container.
    - Attribute values are escaped, like `{{ }}` output.

    A missing file raises FileNotFoundError in development and tests, so a
    renamed or deleted icon breaks the page, and any test that renders it,
    where someone will notice. In production the tag renders nothing instead,
    so one missing icon can't take a page down.
    """
    relative_path = f"svg/{name}.svg"
    absolute_path = find(relative_path)

    if not absolute_path:
        if settings.DEVELOPMENT or settings.TESTING:
            raise FileNotFoundError(
                f"SVG '{name}' not found at '{relative_path}'"
            )
        return ""

    try:
        svg_content = Path(absolute_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        if settings.DEVELOPMENT or settings.TESTING:
            raise
        return ""

    css_class = kwargs.pop("class", None)
    if css_class:
        css_class = conditional_escape(css_class)
        if 'class="' in svg_content:
            svg_content = svg_content.replace(
                'class="', f'class="{css_class} '
            )
        else:
            svg_content = svg_content.replace(
                "<svg", f'<svg class="{css_class}"'
            )

    for key, value in kwargs.items():
        key = key.replace("__", ":")
        key = key.replace("_", "-")
        svg_content = svg_content.replace(
            "<svg", f'<svg {key}="{conditional_escape(value)}"'
        )

    return mark_safe(svg_content.replace("<svg", '<svg role="img"'))

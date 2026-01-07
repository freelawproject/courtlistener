from collections.abc import Callable
from types import MethodType
from typing import Any

from django.forms import BoundField
from django.forms.widgets import Widget
from django.template import Library

from cl.api.models import WEBHOOK_EVENT_STATUS

register = Library()


def _process_field_attributes(
    field: BoundField,
    attr: str,
    process: Callable[..., None],
) -> BoundField:
    # split attribute name and value from 'attr:value' string
    params = attr.split(":", 1)
    attribute = params[0]
    value = params[1] if len(params) == 2 else ""

    # decorate field.as_widget method with updated attributes
    old_as_widget = field.as_widget

    def as_widget(
        self: BoundField,
        widget: Widget | None = None,
        attrs: dict[str, Any] | None = None,
        only_initial: bool = False,
    ) -> str:
        attrs = attrs or {}
        process(widget or self.field.widget, attrs, attribute, value)
        return old_as_widget(widget, attrs, only_initial)

    setattr(field, "as_widget", MethodType(as_widget, field))
    return field


@register.filter("attr")
def set_attr(field: BoundField, attr: str) -> BoundField:
    def process(
        widget: Widget,
        attrs: dict[str, Any],
        attribute: str,
        value: str,
    ) -> None:
        attrs[attribute] = value

    return _process_field_attributes(field, attr, process)


@register.filter
def append_attr(field: BoundField, attr: str) -> BoundField:
    def process(
        widget: Widget,
        attrs: dict[str, Any],
        attribute: str,
        value: str,
    ) -> None:
        if attrs.get(attribute):
            attrs[attribute] += f" {value}"
        elif widget.attrs.get(attribute):
            attrs[attribute] = f"{widget.attrs[attribute]} {value}"
        else:
            attrs[attribute] = value

    return _process_field_attributes(field, attr, process)


@register.filter
def add_class(field: BoundField, css_class: str) -> BoundField:
    return append_attr(field, f"class:{css_class}")


@register.filter
def add_error_class(field: BoundField, css_class: str) -> BoundField:
    if hasattr(field, "errors") and field.errors:
        return add_class(field, css_class)
    return field


@register.filter
def set_data(field: BoundField, data: str) -> BoundField:
    return set_attr(field, f"data-{data}")


@register.filter
def behave(field: BoundField, names: str) -> BoundField:
    """https://github.com/anutron/behavior support"""
    return set_data(field, f"filters:{names}")


@register.filter
def webhook_status_class(event_status: int) -> str:
    """Map a Webhook Event Status to a bootstrap class.

    :param event_status: The WebhookEvent status.
    :return: The corresponding css class.
    """

    match event_status:
        case WEBHOOK_EVENT_STATUS.SUCCESSFUL:
            css_class = "text-success"
        case WEBHOOK_EVENT_STATUS.FAILED:
            css_class = "text-danger"
        case _:
            css_class = "text-warning"
    return css_class

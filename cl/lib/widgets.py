"""Form widgets with CourtListener's new-stack defaults."""

from collections.abc import Mapping
from typing import Any

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.utils.datastructures import MultiValueDict

NEW_STACK_WIDGET_CLASSES = "focus:ring-0 focus:outline-none w-full"
INPUT_TEXT_CLASS = "input-text"


class TextInput(forms.TextInput):
    """Render a text input with CourtListener's new-stack defaults.

    Caller-provided attributes are retained and may override a default when a
    field requires different behavior.
    """

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        """Apply the new-stack class and disable browser autocomplete."""
        attrs = {} if attrs is None else attrs.copy()
        attrs.setdefault("class", NEW_STACK_WIDGET_CLASSES)
        attrs.setdefault("autocomplete", "off")
        super().__init__(attrs=attrs)


class Select(forms.Select):
    """Render a select with CourtListener's new-stack defaults.

    Pass ``input_text=True`` only when the select itself requires the
    ``input-text`` component class. Selects intentionally do not disable
    autocomplete.
    """

    def __init__(
        self,
        attrs: dict[str, Any] | None = None,
        choices: Any = (),
        *,
        input_text: bool = False,
    ) -> None:
        """Apply the new-stack class and optional input-text styling."""
        attrs = {} if attrs is None else attrs.copy()
        attrs.setdefault("class", NEW_STACK_WIDGET_CLASSES)

        classes = str(attrs["class"])
        if input_text and INPUT_TEXT_CLASS not in classes.split():
            attrs["class"] = f"{classes} {INPUT_TEXT_CLASS}"

        super().__init__(attrs=attrs, choices=choices)


class Textarea(forms.Textarea):
    """Render a textarea with CourtListener's new-stack defaults.

    Caller-provided attributes are retained and may override a default when a
    field requires different behavior.
    """

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        """Apply the new-stack class and a compact default height."""
        attrs = {} if attrs is None else attrs.copy()
        attrs.setdefault("class", NEW_STACK_WIDGET_CLASSES)
        attrs.setdefault("rows", 4)

        super().__init__(attrs=attrs)

    def value_from_datadict(
        self,
        data: Mapping[str, Any],
        files: MultiValueDict[str, UploadedFile],
        name: str,
    ) -> Any:
        """Return the submitted text with CRLF line breaks turned into LF.

        Browsers count a line break as one character for maxlength but submit
        it as CRLF, so without this a value that fits the textarea can fail
        the field's max_length. Fields read the value through here before
        they clean or validate it.
        """
        value = super().value_from_datadict(data, files, name)
        if isinstance(value, str):
            return value.replace("\r\n", "\n")
        return value

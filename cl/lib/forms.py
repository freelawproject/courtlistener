"""Shared form base classes."""

from typing import Any

from django import forms


class BootstrapModelForm(forms.ModelForm):
    """Model form that adds Bootstrap's ``form-control`` class to its visible fields."""

    # Add form-control to all fields
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Build the form, adding ``form-control`` to each visible field's classes."""
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            attrs = visible.field.widget.attrs
            try:
                attrs["class"] += " form-control"
            except KeyError:
                attrs["class"] = "form-control"

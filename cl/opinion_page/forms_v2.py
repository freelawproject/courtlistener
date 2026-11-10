from typing import Any

from cl.lib import widgets
from cl.opinion_page.forms import (
    DocketEntryFilterForm as V1DocketEntryFilterForm,
)


class DocketEntryFilterForm(V1DocketEntryFilterForm):
    """The v1 docket entry filter form, with new-stack widgets and labels."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Build the v1 form, then swap in the v2 widgets and labels."""
        super().__init__(*args, **kwargs)
        number_attrs = {
            "type": "number",
            "min": 0,
            "class": widgets.NEW_STACK_WIDGET_CLASSES + " no-spinner",
        }
        self.fields["entry_gte"].label = "Documents from"
        self.fields["entry_gte"].widget = widgets.TextInput(
            attrs={"placeholder": "From", **number_attrs}
        )
        self.fields["entry_lte"].label = "Documents to"
        self.fields["entry_lte"].widget = widgets.TextInput(
            attrs={"placeholder": "To", **number_attrs}
        )
        date_attrs = {"placeholder": "mm/dd/yyyy", "autocomplete": "off"}
        self.fields["filed_after"].widget = widgets.TextInput(
            attrs={**date_attrs, "data-flatpickr-after": ""}
        )
        self.fields["filed_before"].widget = widgets.TextInput(
            attrs={**date_attrs, "data-flatpickr-before": ""}
        )

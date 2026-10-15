from django import forms

from cl.lib import widgets
from cl.search.fields import CeilingDateField, FloorDateField


class DocketEntryFilterForm(forms.Form):
    """Filters and sorts the entries shown on a docket page, bound to the
    request's GET params."""

    ASCENDING = "asc"
    DESCENDING = "desc"
    DOCKET_ORDER_BY_CHOICES = (
        (ASCENDING, "Ascending"),
        (DESCENDING, "Descending"),
    )
    entry_gte = forms.IntegerField(
        required=False,
        min_value=0,
        label="Documents from",
        widget=widgets.TextInput(
            attrs={
                "placeholder": "From",
                "type": "number",
                "min": 0,
                "class": widgets.NEW_STACK_WIDGET_CLASSES + " no-spinner",
            }
        ),
    )
    entry_lte = forms.IntegerField(
        required=False,
        min_value=0,
        label="Documents to",
        widget=widgets.TextInput(
            attrs={
                "placeholder": "To",
                "type": "number",
                "min": 0,
                "class": widgets.NEW_STACK_WIDGET_CLASSES + " no-spinner",
            }
        ),
    )
    filed_after = FloorDateField(
        required=False,
        label="Filed After",
        widget=widgets.TextInput(
            attrs={
                "placeholder": "mm/dd/yyyy",
                "autocomplete": "off",
                "data-flatpickr-after": "",
            }
        ),
    )
    filed_before = CeilingDateField(
        required=False,
        label="Filed Before",
        widget=widgets.TextInput(
            attrs={
                "placeholder": "mm/dd/yyyy",
                "autocomplete": "off",
                "data-flatpickr-before": "",
            }
        ),
    )
    order_by = forms.ChoiceField(
        choices=DOCKET_ORDER_BY_CHOICES,
        required=False,
        label="Ordering",
        initial=ASCENDING,
        widget=forms.Select(),
    )

    def has_filters(self) -> bool:
        """Whether the bound data carries any filter or search param.

        Checks the raw data rather than cleaned_data so an invalid value
        (say, a non-numeric entry number) still counts: the user asked for a
        filter either way. The docket page uses this to pick between the
        "no entries yet" and the "nothing matches your filters" empty state.
        """
        # order_by only reorders the same entries, so an empty docket
        # sorted either way still gets the "no entries yet" copy.
        return any(
            self.data.get(name) for name in self.fields if name != "order_by"
        )

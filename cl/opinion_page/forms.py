from django import forms

from cl.search.fields import CeilingDateField
from cl.search.fields import FloorDateField


class CitationRedirectorForm(forms.Form):
    volume = forms.IntegerField(
        widget=forms.TextInput(attrs={
            'class': 'form-control input-lg',
            'placeholder': 'Volume',
        }),
        required=True,
    )
    reporter = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control input-lg',
            'placeholder': 'Reporter',
        }),
        required=True,
    )
    page = forms.IntegerField(
        widget=forms.TextInput(attrs={
            'class': 'form-control input-lg',
            'placeholder': 'Page',
        }),
        required=True,
    )


class DocketEntryFilterForm(forms.Form):
    ASCENDING = 'asc'
    DESCENDING = 'desc'
    DOCKET_ORDER_BY_CHOICES = (
        (ASCENDING, 'Ascending'),
        (DESCENDING, 'Descending'),
    )
    entry_gte = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off'
        })
    )
    entry_lte = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off'
        })
    )
    filed_after = FloorDateField(
        required=False,
        label='Filed After',
        widget=forms.TextInput(attrs={
            'placeholder': 'YYYY-MM-DD',
            'class': 'form-control',
            'autocomplete': 'off'
        })
    )
    filed_before = CeilingDateField(
        required=False,
        label='Filed Before',
        widget=forms.TextInput(attrs={
            'placeholder': 'YYYY-MM-DD',
            'class': 'form-control',
            'autocomplete': 'off'
        })
    )
    order_by = forms.ChoiceField(
        choices=DOCKET_ORDER_BY_CHOICES,
        required=False,
        label='Ordering',
        initial=ASCENDING,
        widget=forms.Select()
    )

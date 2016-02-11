from django import forms


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

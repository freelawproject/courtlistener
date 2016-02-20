from django import forms


class ContactForm(forms.Form):
    name = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control'}
        )
    )

    email = forms.EmailField(
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'form-control'}
        )
    )

    subject = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={'class': 'form-control'}
        )
    )

    message = forms.CharField(
        min_length=20,
        widget=forms.Textarea(
            attrs={'class': 'form-control'}
        )
    )

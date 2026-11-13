from django import forms


class SSOStartForm(forms.Form):
    """The one field on the "sign in with SSO" page."""

    email = forms.EmailField(
        label="Your work email address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control input-lg",
                "autocomplete": "email",
                "autofocus": "on",
            }
        ),
    )

import re
from typing import Any, Dict

from django import forms
from hcaptcha.fields import hCaptchaField


class ContactForm(forms.Form):
    name = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    email = forms.EmailField(
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    # This is actually the "Subject" field, but we call it the phone_number
    # field to defeat spam.
    phone_number = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off"}
        ),
    )

    message = forms.CharField(
        min_length=20, widget=forms.Textarea(attrs={"class": "form-control"})
    )

    hcaptcha = hCaptchaField()

    def clean(self) -> Dict[str, Any] | None:
        cleaned_data: dict[str, Any] | None = super().clean()
        if cleaned_data is None:
            return cleaned_data
        subject = cleaned_data.get("phone_number", "")
        message = cleaned_data.get("message", "")
        regex = re.compile(
            r"block (from)?search engines?|block pages|ccpa|de-?index|"
            r"delete link|dmca|expunge|opt out|no ?index|stop posting|"
            r"remov(e|al)|take down",
            re.I,
        )
        if re.search(regex, subject) and "http" not in message.lower():
            msg = (
                "This appears to be a removal request, but you did not "
                "include a link. You must include a link for a request to be "
                "valid."
            )
            self.add_error("message", msg)
        return cleaned_data

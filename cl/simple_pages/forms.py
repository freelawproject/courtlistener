import re
from typing import Dict

from django import forms
from django.core.exceptions import ValidationError


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

    quiz = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off"},
        ),
    )

    def clean_quiz(self) -> Dict[str, str]:
        data = self.cleaned_data["quiz"]
        if data.strip().lower() != "blue":
            raise ValidationError("Please say the sky is blue.")
        return data

    def clean(self) -> None:
        cleaned_data = super().clean()
        subject = cleaned_data["phone_number"]
        message = cleaned_data["message"]
        regex = re.compile(
            r"remov(e|al)|take down request|opt out|de-index|delete link"
            r"|no ?index|block (from)?search engines?|block pages",
            re.I,
        )
        if re.search(regex, subject) and "http" not in message.lower():
            msg = (
                "This appears to be a removal request, but you did not "
                "include a link. You must include a link for a request to be "
                "valid."
            )
            self.add_error("message", msg)

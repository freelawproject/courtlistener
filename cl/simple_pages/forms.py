import re
from typing import Any, Dict

from django import forms
from hcaptcha.fields import hCaptchaField


class ContactForm(forms.Form):
    SUPPORT_REQUEST = "support"
    API_HELP = "api"
    DATA_QUALITY = "data_quality"
    RECAP_BUG = "recap"
    REMOVAL_REQUEST = "removal"
    MEMBERSHIPS = "memberships"

    ISSUE_TYPE_CHOICES = [
        (SUPPORT_REQUEST, "General Support"),
        (API_HELP, "Data or API Help"),
        (DATA_QUALITY, "Report Data Quality Problem"),
        (RECAP_BUG, "RECAP Extension Bug"),
        (REMOVAL_REQUEST, "Case Removal Request"),
        (MEMBERSHIPS, "Memberships or Donations"),
    ]

    VALID_ISSUE_TYPES = [choice[0] for choice in ISSUE_TYPE_CHOICES]

    name = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    email = forms.EmailField(
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    issue_type = forms.ChoiceField(
        choices=ISSUE_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
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
        is_removal_request = (
            re.search(regex, subject)
            or cleaned_data.get("issue_type", "") == self.REMOVAL_REQUEST
        )
        if is_removal_request and "http" not in message.lower():
            msg = (
                "This appears to be a removal request, but you did not "
                "include a link. You must include a link for a request to be "
                "valid."
            )
            self.add_error("message", msg)
        return cleaned_data

    def get_issue_type_display(self) -> str:
        value = self.cleaned_data.get("issue_type", "")
        return dict(self.ISSUE_TYPE_CHOICES).get(value, "Unidentified Type")

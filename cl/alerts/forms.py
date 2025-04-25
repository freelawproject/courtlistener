from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import HiddenInput, Select, TextInput
from hcaptcha.fields import hCaptchaField

from cl.alerts.models import Alert
from cl.alerts.utils import is_match_all_query


class CreateAlertForm(ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_rate(self):
        rate = self.cleaned_data["rate"]
        is_a_member = self.user.profile.is_member
        if rate == "rt" and not is_a_member:
            # Somebody is trying to hack past the JS/HTML block on the front
            # end. Don't let them create the alert until they've donated.
            raise ValidationError(
                "You must be a Member to create Real Time alerts."
            )
        else:
            return rate

    def clean_query(self):
        """Validate that the query is not a match-all query, as these alerts
        would trigger for every new document ingested or updated.
        """
        query = self.cleaned_data["query"]
        match_all_query = is_match_all_query(query)
        if match_all_query:
            raise ValidationError(
                "You can't create a match-all alert. Please try narrowing your query."
            )
        else:
            return query

    class Meta:
        model = Alert
        exclude = ("user", "secret_key")
        fields = ("name", "query", "rate", "alert_type")
        widgets = {
            "query": HiddenInput(),
            "name": TextInput(attrs={"class": "form-control"}),
            "rate": Select(attrs={"class": "form-control"}),
            "alert_type": HiddenInput(),
        }


class DocketAlertConfirmForm(forms.Form):
    hcaptcha = hCaptchaField(size="invisible")

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import HiddenInput, Select, TextInput
from hcaptcha.fields import hCaptchaField

from cl.alerts.models import Alert


class CreateAlertForm(ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_rate(self):
        rate = self.cleaned_data["rate"]
        not_donated_enough = (
            self.user.profile.total_donated_last_year
            < settings.MIN_DONATION["rt_alerts"]
        )
        if rate == "rt" and not_donated_enough:
            # Somebody is trying to hack past the JS/HTML block on the front
            # end. Don't let them create the alert until they've donated.
            raise ValidationError(
                "You must donate more than $10 per year to create Real Time "
                "alerts."
            )
        else:
            return rate

    class Meta:
        model = Alert
        exclude = ("user", "secret_key")
        fields = (
            "name",
            "query",
            "rate",
        )
        widgets = {
            "query": HiddenInput(),
            "name": TextInput(attrs={"class": "form-control"}),
            "rate": Select(attrs={"class": "form-control"}),
        }


class DocketAlertConfirmForm(forms.Form):
    hcaptcha = hCaptchaField(size="invisible")

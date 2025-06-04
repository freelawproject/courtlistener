from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import HiddenInput, Select, TextInput
from hcaptcha.fields import hCaptchaField

from cl.alerts.models import Alert
from cl.alerts.utils import is_match_all_query
from cl.search.models import SEARCH_TYPES


class CreateAlertForm(ModelForm):
    ALERT_INCLUSION_CHOICES = [
        (SEARCH_TYPES.DOCKETS, "Notifications on new cases only"),
        (
            SEARCH_TYPES.RECAP,
            "Notifications on both new cases and new filings",
        ),
    ]
    alert_type = forms.ChoiceField(
        label="What should we include in your alerts?",
        choices=ALERT_INCLUSION_CHOICES,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        initial = kwargs.get("initial", {})
        super().__init__(*args, **kwargs)

        current_type = None
        # First look at the original alert_type for new alerts / errors.
        if "original_alert_type" in initial:
            current_type = initial["original_alert_type"]

        # Otherwise look at the existing instance alert_type for Edit Alert.
        elif getattr(self, "instance", None) and getattr(
            self.instance, "pk", None
        ):
            current_type = getattr(self.instance, "alert_type", None)

        # Hide the alert_type field for search types other than RECAP.
        if current_type not in (SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS):
            self.fields["alert_type"].widget = HiddenInput()
            # Restore the original valid alert_type field choices, since
            # they were overridden for RECAP
            self.fields[
                "alert_type"
            ].choices = SEARCH_TYPES.SUPPORTED_ALERT_TYPES

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

    def clean_alert_type(self):
        alert_type = self.cleaned_data["alert_type"]
        try:
            # Update the instance's alert_type to compare it with its old value
            self.instance.alert_type = alert_type
            self.instance.alert_type_changed()
        except ValidationError as e:
            raise ValidationError(e.message_dict["alert_type"])
        return alert_type

    class Meta:
        model = Alert
        exclude = ("user", "secret_key")
        fields = ("name", "query", "rate", "alert_type")
        widgets = {
            "query": HiddenInput(),
            "name": TextInput(attrs={"class": "form-control"}),
            "rate": Select(attrs={"class": "form-control"}),
        }


class DocketAlertConfirmForm(forms.Form):
    hcaptcha = hCaptchaField(size="invisible")

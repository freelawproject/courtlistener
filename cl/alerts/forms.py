from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import HiddenInput, Select, TextInput
from django.urls import reverse
from django.utils.html import format_html
from hcaptcha.fields import hCaptchaField

from cl.alerts.constants import RECAP_ALERT_QUOTAS
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

        self.current_type = None
        # First look at the original alert_type for new alerts / errors.
        if "original_alert_type" in initial:
            self.current_type = initial["original_alert_type"]

        # Otherwise look at the existing instance alert_type for Edit Alert.
        elif getattr(self, "instance", None) and getattr(
            self.instance, "pk", None
        ):
            self.current_type = getattr(self.instance, "alert_type", None)

        # Hide the alert_type field for search types other than RECAP.
        if self.current_type not in (SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS):
            self.fields["alert_type"].widget = HiddenInput()
            # Restore the original valid alert_type field choices, since
            # they were overridden for RECAP
            self.fields[
                "alert_type"
            ].choices = SEARCH_TYPES.SUPPORTED_ALERT_TYPES

    def clean_rate(self):
        rate = self.cleaned_data["rate"]

        alert_being_edited = self.instance and self.instance.pk
        if alert_being_edited and rate == Alert.OFF:
            # Don't check quotas when the user disables their alert.
            return rate

        quotas_key = (
            Alert.REAL_TIME if rate == Alert.REAL_TIME else "other_rates"
        )
        quotas = RECAP_ALERT_QUOTAS[quotas_key]
        is_member = self.user.profile.is_member
        if is_member:
            level_key = self.user.membership.level
        else:
            level_key = "free"

        flp_membership = "https://donate.free.law/forms/membership"
        # Only members can create RT alerts
        if rate == Alert.REAL_TIME and not is_member:
            msg = format_html(
                "You must be a <a href='{}' target='_blank'>member</a> to create Real Time alerts.",
                flp_membership,
            )
            raise ValidationError(msg)

        # Only check quotas for RECAP or DOCKETS alerts
        if self.current_type in {SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS}:
            allowed = quotas.get(level_key, quotas.get("free", 0))

            query_params = {"user": self.user}
            if rate == Alert.REAL_TIME:
                query_params["rate"] = Alert.REAL_TIME
            else:
                query_params["rate__in"] = [
                    Alert.DAILY,
                    Alert.WEEKLY,
                    Alert.MONTHLY,
                ]
            alerts_count = Alert.objects.filter(
                **query_params,
                alert_type__in=[SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS],
            )
            if alert_being_edited:
                # exclude the alert being edited from the count
                alerts_count = alerts_count.exclude(pk=self.instance.pk)
            used = alerts_count.count()
            profile_url = reverse("profile_alerts")

            if used + 1 > allowed:
                if is_member:
                    msg = format_html(
                        "You've used all of the alerts included with your membership. "
                        "To create this alert, <a href='{}' target='_blank'>upgrade your membership</a> or "
                        "<a href='{}'>disable a RECAP Alert</a>.",
                        flp_membership,
                        profile_url,
                    )
                else:
                    msg = format_html(
                        "To create more than {} alerts and to gain access to real time alerts, "
                        "please join <a href='{}' target='_blank'>Free Law project</a> as a member.",
                        quotas.get("free"),
                        flp_membership,
                    )
                raise ValidationError(msg)

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
        # On alert updates, validates that the alert_type hasn't changed in a
        # disallowed way.
        alert_type = self.cleaned_data["alert_type"]
        try:
            # Update the instance's alert_type to compare it with its old value
            self.instance.alert_type = alert_type
            self.instance.validate_alert_type_change()
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

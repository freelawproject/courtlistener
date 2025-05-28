from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import HiddenInput, Select, TextInput
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
        quotas_key = (
            Alert.REAL_TIME if rate == Alert.REAL_TIME else "other_rates"
        )
        quotas = RECAP_ALERT_QUOTAS[quotas_key]
        is_member = self.user.profile.is_member
        if is_member:
            level_key = self.user.membership.level
            plan_name = self.user.membership.get_level_display()
        else:
            level_key, plan_name = "free", "Free"

        # Only members can create RT alerts
        if rate == Alert.REAL_TIME and not is_member:
            raise ValidationError(
                "You must be a Member to create Real Time alerts."
            )

        # Only check quotas for RECAP or DOCKETS alerts
        if self.current_type in {SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS}:
            allowed = quotas.get(level_key, quotas.get("free", 0))
            # Count usage
            if rate == Alert.REAL_TIME:
                used = Alert.objects.filter(
                    user=self.user,
                    rate=Alert.REAL_TIME,
                    alert_type__in=[SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS],
                ).count()
                label = dict(Alert.FREQUENCY)[Alert.REAL_TIME]
            else:
                used = Alert.objects.filter(
                    user=self.user,
                    rate__in=[Alert.DAILY, Alert.WEEKLY, Alert.MONTHLY],
                ).count()
                label = "Daily, Weekly or Monthly"

            if used >= allowed:
                raise ValidationError(
                    f"Your {plan_name} plan allows only {allowed} {label} alerts; "
                    f"you already have {used}."
                )

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
        }


class DocketAlertConfirmForm(forms.Form):
    hcaptcha = hCaptchaField(size="invisible")

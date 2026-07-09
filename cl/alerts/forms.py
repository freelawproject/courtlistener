from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import HiddenInput, Select, TextInput
from django.urls import reverse
from django.utils.html import format_html
from hcaptcha.fields import hCaptchaField

from cl.alerts.constants import (
    FLP_MEMBERSHIP_URL,
    LEGACY_MEMBERSHIP_HELP_URL,
    MEMBERSHIP_UPGRADE_BASE_URL,
)
from cl.alerts.models import Alert
from cl.alerts.utils import (
    AlertLimitViolation,
    check_alert_limits,
    is_match_all_query,
)
from cl.donate.models import NeonMembershipLevel
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
        result = check_alert_limits(
            self.user,
            rate,
            self.current_type,
            exclude_alert_pk=self.instance.pk if alert_being_edited else None,
        )
        match result.violation:
            case AlertLimitViolation.REAL_TIME_NOT_ALLOWED:
                raise ValidationError(
                    format_html(
                        "You must be a <a href='{}' target='_blank'>member</a> to create Real Time alerts.",
                        FLP_MEMBERSHIP_URL,
                    )
                )
            case AlertLimitViolation.MEMBER_QUOTA_EXCEEDED:
                membership = self.user.membership
                if membership.level == NeonMembershipLevel.LEGACY:
                    # Legacy memberships can't be upgraded online, so point
                    # them at the help page instead of the Neon upgrade flow.
                    raise ValidationError(
                        format_html(
                            "You've used all of the alerts included with your legacy membership. "
                            "Legacy memberships can't be upgraded online, but "
                            "<a href='{}' target='_blank'>here's how to get more features</a>, or "
                            "<a href='{}'>disable a RECAP Alert</a>.",
                            LEGACY_MEMBERSHIP_HELP_URL,
                            reverse("profile_search_alerts"),
                        )
                    )
                upgrade_flp_membership = (
                    f"{MEMBERSHIP_UPGRADE_BASE_URL}{membership.neon_id}"
                )
                raise ValidationError(
                    format_html(
                        "You've used all of the alerts included with your membership. "
                        "To create this alert, <a href='{}' target='_blank'>upgrade your membership</a> or "
                        "<a href='{}'>disable a RECAP Alert</a>.",
                        upgrade_flp_membership,
                        reverse("profile_search_alerts"),
                    )
                )
            case AlertLimitViolation.FREE_QUOTA_EXCEEDED:
                raise ValidationError(
                    format_html(
                        "To create more than {} alerts and to gain access to real time alerts, "
                        "please join <a href='{}' target='_blank'>Free Law project</a> as a member.",
                        result.free_quota,
                        FLP_MEMBERSHIP_URL,
                    )
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

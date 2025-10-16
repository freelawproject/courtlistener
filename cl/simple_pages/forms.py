import re
from typing import Any

from django import forms
from hcaptcha.fields import hCaptchaField


class ContactForm(forms.Form):
    SUPPORT_REQUEST = "support"
    PARTNERSHIPS = "partnerships"
    API_HELP = "api"
    DATA_QUALITY = "data_quality"
    RECAP_BUG = "recap"
    REMOVAL_REQUEST = "removal"
    MEMBERSHIPS = "memberships"

    ISSUE_TYPE_CHOICES = [
        (SUPPORT_REQUEST, "General Support"),
        (PARTNERSHIPS, "Partnership Inquiry"),
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

    TECH_ISSUE_TYPES = {API_HELP, RECAP_BUG}

    # Build actual choices with additional, invalid options
    ISSUE_TYPE_FORM_CHOICES = [issue_type for issue_type in ISSUE_TYPE_CHOICES]
    # Add empty default to force deliberate choice
    ISSUE_TYPE_FORM_CHOICES.insert(0, ("", "Select a topic"))
    # Add legal help option to redirect users to third party resources
    ISSUE_TYPE_FORM_CHOICES.append(("legal", "Legal Help"))
    issue_type = forms.ChoiceField(
        choices=ISSUE_TYPE_FORM_CHOICES,
        widget=forms.Select(
            attrs={"class": "form-control", "x-on:change": "onUpdate"}
        ),
        label="How can we help?",
    )

    # This is actually the "Subject" field, but we call it the phone_number
    # field to defeat spam.
    phone_number = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off"}
        ),
        label="Subject",
    )

    message = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "x-ref": "message"}
        ),
    )

    hcaptcha = hCaptchaField()

    # PARTNERSHIPS

    PARTNER_BACKGROUND_CHOICES = [
        ("founder", "Founder / Co-founder"),
        ("dev", "Developer / Engineer"),
        ("legal", "Legal Professional"),
        ("academic", "Researcher / Academic"),
        ("investor", "Investor / VC"),
        ("other", "Other"),
    ]
    partner_background = forms.MultipleChoiceField(
        required=False,
        choices=PARTNER_BACKGROUND_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    partner_background_other = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    partner_current_work = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.TextInput(
            attrs={"class": "form-control", "data-required-contextually": ""}
        ),
        label="What are you currently working on?",
    )
    partner_prior_outreach = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "data-required-contextually": ""}
        ),
        label="What have you tried, or which organizations have you already talked to?",
    )

    PARTNER_TEAM_SIZE_CHOICES = [
        ("", "Select a team size"),
        ("solo", "Solo"),
        ("2_5", "2–5"),
        ("6_10", "6–10"),
        ("11_plus", "11+"),
    ]
    partner_team_size = forms.ChoiceField(
        required=False,
        choices=PARTNER_TEAM_SIZE_CHOICES,
        widget=forms.Select(
            attrs={"class": "form-control", "data-required-contextually": ""}
        ),
        label="How many people are on your team?",
    )

    partner_founded_year = forms.IntegerField(
        required=False,
        min_value=1800,
        max_value=9999,
        widget=forms.TextInput(
            attrs={"class": "form-control", "data-required-contextually": ""}
        ),
        label="When was your company founded? (Year)",
    )

    PARTNER_FUNDING_TOTAL_CHOICES = [
        ("", "Select an option"),
        ("none", "None"),
        ("lt_50k", "<50k"),
        ("50_250k", "50k–250k"),
        ("250k_1m", "250k–1m"),
        ("gt_1m", "1m+"),
    ]
    partner_funding_total = forms.ChoiceField(
        required=False,
        choices=PARTNER_FUNDING_TOTAL_CHOICES,
        widget=forms.Select(
            attrs={"class": "form-control", "data-required-contextually": ""}
        ),
        label="How much funding have you raised so far?",
    )

    PARTNER_FUNDING_STAGE_CHOICES = [
        ("", "Select an option"),
        ("not_pursuing", "Not pursuing"),
        ("fundraising", "Fundraising"),
        ("pre_seed", "Pre-seed"),
        ("seed", "Seed"),
        ("series_a_plus", "Series A+"),
    ]
    partner_funding_stage = forms.ChoiceField(
        required=False,
        choices=PARTNER_FUNDING_STAGE_CHOICES,
        widget=forms.Select(
            attrs={"class": "form-control", "data-required-contextually": ""}
        ),
        label="What's the current status of your VC funding?",
    )

    partner_ideal_outcome = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "data-required-contextually": ""}
        ),
        label="What's the ideal outcome you'd like from connecting with us?",
    )

    # TECH SUPPORT

    tech_description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "data-required-contextually": ""}
        ),
        label="Please describe the issue",
    )
    tech_started_at = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="When did this issue start? (date or approx.)",
    )
    tech_steps_tried = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control"}),
        label="What troubleshooting steps have you already tried?",
    )
    tech_links = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control"}),
        label="Links to screenshots, error messages, or logs (if any)",
    )

    def clean(self) -> dict[str, Any] | None:
        cleaned_data: dict[str, Any] | None = super().clean()
        if cleaned_data is None:
            return cleaned_data
        subject = cleaned_data.get("phone_number", "")

        issue = cleaned_data.get("issue_type", "")

        # Partnerships: check for required fields
        if issue == self.PARTNERSHIPS:
            required_partnership_fields = {
                "partner_current_work": "Please tell us what you're working on.",
                "partner_prior_outreach": "Please tell us what you've tried and/or who you've contacted about this.",
                "partner_team_size": "Please select your team size.",
                "partner_founded_year": "Please tell us when your organization was founded.",
                "partner_ideal_outcome": "What are your expectations from contacting us?",
                "partner_funding_total": "Please tell us how much funding you've raised so far.",
                "partner_funding_stage": "Please tell us the status of your VC funding if any.",
            }
            for field, message in required_partnership_fields.items():
                if not cleaned_data.get(field):
                    self.add_error(field, message)

            backgrounds = cleaned_data.get("partner_background", []) or []
            if len(backgrounds) == 0:
                self.add_error(
                    "partner_background_other",
                    "Please specify at least one background.",
                )
            elif "other" in backgrounds and not cleaned_data.get(
                "partner_background_other"
            ):
                # If "other" is checked, require the description
                self.add_error(
                    "partner_background_other",
                    "Please specify your background.",
                )

        # Technical support: always require a description
        if issue in self.TECH_ISSUE_TYPES:
            if not cleaned_data.get("tech_description"):
                self.add_error(
                    "tech_description", "Please describe the issue."
                )

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

    def label_for(self, field_name: str, separator: str = ", ") -> str | None:
        """Return the human label for a ChoiceField/MultipleChoiceField value (or None)."""
        value = self.cleaned_data.get(field_name)
        if not value:
            return None
        choices = dict(getattr(self.fields[field_name], "choices", {}))
        return (
            separator.join([choices[v] for v in value if v in choices])
            if type(value) is list
            else choices.get(value)
        )

    def email_subject(self) -> str:
        """Subject line for this submission."""
        return f"[CourtListener] Contact: {self.cleaned_data['phone_number']}"

    def render_email_body(self, user_agent: str = "Unknown") -> str:
        """Plain-text email body built from cleaned_data. Includes all relevant fields for the issue type."""
        cd = self.cleaned_data
        issue_type_label = self.get_issue_type_display()

        lines: list[str] = [
            f"Subject: {cd.get('phone_number', '')}",
            f"From: {cd.get('name', '')}",
            f"User Email: <{cd.get('email', '')}>",
            f"Issue Type: {issue_type_label}",
            "",
        ]

        # Partnerships
        if cd.get("issue_type") == self.PARTNERSHIPS:
            bg_labels = self.label_for("partner_background", separator=", ")
            lines.append(f"Background: {bg_labels}")
            lines.append(
                f"Background (other): {cd.get('partner_background_other', '')}"
            )
            lines.append(f"Current Work: {cd.get('partner_current_work')}")
            team_label = self.label_for("partner_team_size")
            lines.append(f"Team Size: {team_label if team_label else ''}")
            lines.append(f"Founded Year: {cd.get('partner_founded_year', '')}")
            funding_total_label = self.label_for("partner_funding_total")
            lines.append(
                f"Funding Total: {funding_total_label if funding_total_label else ''}"
            )
            funding_stage_label = self.label_for("partner_funding_stage")
            lines.append(
                f"Funding Stage: {funding_stage_label if funding_stage_label else ''}"
            )
            lines.append(f"Prior Outreach: {cd.get('partner_prior_outreach')}")
            lines.append(f"Ideal Outcome: {cd.get('partner_ideal_outcome')}")
            lines.append("")

        # Technical
        elif cd.get("issue_type") in self.TECH_ISSUE_TYPES:
            lines.append("Technical Description:")
            lines.append(cd.get("tech_description", "-"))
            lines.append("")
            lines.append(f"Started At: {cd.get('tech_started_at', '')}")
            lines.append(f"Steps Tried: {cd.get('tech_steps_tried', '')}")
            lines.append(f"Links: {cd.get('tech_links', '')}")
            lines.append("")

        lines.append("Message:")
        lines.append(cd.get("message", ""))
        lines.append("")
        lines.append(f"Browser: {user_agent}")

        return "\n".join(lines)

import re
from typing import Any

from django import forms
from django.conf import settings
from django.urls import reverse
from django.utils.html import format_html
from hcaptcha.fields import hCaptchaField

SEALING_KEYWORDS_REGEX = re.compile(
    r"urgent|seal(ing|ed)?|redact(ed)?|pseudonym|anonymi(ty|ze)|"
    r"press[\.\s]?coverage|time[\.\s]?sensitive",
    re.I,
)


class ContactForm(forms.Form):
    SUPPORT_REQUEST = "support"
    PARTNERSHIPS = "partnerships"
    API_HELP = "api"
    MCP = "mcp"
    DATA_QUALITY = "data_quality"
    DMCA_COMPLAINT = "dmca_complaint"
    RECAP_BUG = "recap"
    REMOVAL_REQUEST = "removal"
    MEMBERSHIPS = "memberships"
    VOLUNTEERING = "volunteering"

    ISSUE_TYPE_CHOICES = [
        (SUPPORT_REQUEST, "General Support"),
        (PARTNERSHIPS, "Partnership Inquiry"),
        (API_HELP, "Data or API Support"),
        (MCP, "MCP Server"),
        (DATA_QUALITY, "Report Data Quality Problem"),
        (DMCA_COMPLAINT, "DMCA Complaint"),
        (RECAP_BUG, "RECAP Extension Bug"),
        (REMOVAL_REQUEST, "Case Removal Request"),
        (MEMBERSHIPS, "Memberships or Donations"),
        (VOLUNTEERING, "Volunteering"),
    ]

    VALID_ISSUE_TYPES = [choice[0] for choice in ISSUE_TYPE_CHOICES]
    TECH_ISSUE_TYPES = {API_HELP, MCP, RECAP_BUG}
    DOCUMENTATION_CHECK_TYPES = {SUPPORT_REQUEST, API_HELP, MCP, RECAP_BUG}

    name = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    # Required for anonymous submitters, ignored for logged-in submitters
    # This allows support staff to trust the email provided to Zoho Desk be
    # auth'ed users.
    email = forms.EmailField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    # Build actual choices with additional, invalid options
    ISSUE_TYPE_FORM_CHOICES = [issue_type for issue_type in ISSUE_TYPE_CHOICES]
    # Add empty default to force deliberate choice
    ISSUE_TYPE_FORM_CHOICES.insert(0, ("", "Select a topic"))
    # Add legal help option to redirect users to third party resources
    ISSUE_TYPE_FORM_CHOICES.append(("legal", "Legal Help"))
    issue_type = forms.ChoiceField(
        choices=ISSUE_TYPE_FORM_CHOICES,
        widget=forms.Select(
            attrs={"class": "form-control", "x-on:change": "onUpdateIssueType"}
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

    checked_documentation = forms.BooleanField(
        required=False,
    )

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
        widget=forms.CheckboxSelectMultiple(
            attrs={"x-on:change": "onUpdatePartnerBackground"}
        ),
    )
    partner_background_other = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "x-ref": "otherBackground",
                "x-on:click": "checkOtherBackground",
            },
        ),
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
        ("11_25", "11-25"),
        ("26_100", "26-100"),
        ("101_1000", "101-1,000"),
        ("1001_10000", "1,001-10,000"),
        ("10001_plus", "10,001+"),
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
        ("lt_50k", "< $50k"),
        ("50_250k", "$50k–$250k"),
        ("250k_1m", "$250k–$1m"),
        ("gt_1m", "$1m+"),
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

    def __init__(
        self,
        *args: Any,
        is_authenticated: bool = False,
        account_email: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.is_authenticated = is_authenticated
        self.account_email = account_email
        # reverse() can't be called at class definition time because
        # Django's URL configuration isn't loaded yet during import.
        help_url = reverse("help_home")
        self.fields["checked_documentation"].label = format_html(
            'I have reviewed the <a href="https://wiki.free.law">wiki</a>,'
            ' <a href="{}">documentation</a>, and'
            ' <a href="https://github.com/freelawproject/courtlistener/'
            'discussions">discussion forum</a>'
            " for an answer to my question.",
            help_url,
        )

    def clean(self) -> dict[str, Any] | None:
        cleaned_data: dict[str, Any] | None = super().clean()
        if cleaned_data is None:
            return cleaned_data
        subject = cleaned_data.get("phone_number", "")

        issue = cleaned_data.get("issue_type", "")

        email = self._get_email()
        if not self.is_authenticated and not email:
            # Only unauthenticated users have the email field on the front end
            # and the possibility of it being left blank.
            self.add_error("email", "Please provide your email address.")

        # Require documentation checkbox for support-type issues
        if issue in self.DOCUMENTATION_CHECK_TYPES and not cleaned_data.get(
            "checked_documentation"
        ):
            self.add_error(
                "checked_documentation",
                "Please review our documentation before submitting.",
            )

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
        elif issue in self.TECH_ISSUE_TYPES:
            if not cleaned_data.get("tech_description"):
                self.add_error(
                    "tech_description", "Please describe the issue."
                )

        # Neither Partnership inquiry nor Tech support => no additional fields so message is required:
        else:
            if not cleaned_data.get("message"):
                self.add_error("message", "Please include a message.")

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

    def render_email_body(
        self,
        user_agent: str = "Unknown",
        logged_in_info: dict[str, Any] | None = None,
    ) -> str:
        """Build the HTML body for the Zoho Desk ticket description.

        Each rendered field is separated by a blank line, and multi-line
        user input (e.g. the Message textarea) has its newlines converted
        to ``<br>`` so they render in Zoho Desk's HTML description.

        :param user_agent: The submitter's browser User-Agent string.
        :param logged_in_info: If the submitter was authenticated, a dict
            with their ``username``, ``email``, and ``email_confirmed``
            status. ``None`` for anonymous submissions.
        :return: HTML string suitable for the Zoho Desk ``description``
            field.
        """
        cd = self.cleaned_data

        def line(label: str, value: Any) -> str:
            # Convert newlines so multi-line input renders as multiple
            # lines in Zoho Desk's HTML description.
            text = "" if value is None else str(value)
            return f"{label}: {text}".replace("\n", "<br>")

        lines: list[str] = [
            line("Subject", cd.get("phone_number", "")),
            line("From", cd.get("name", "")),
            line("Issue Type", self.get_issue_type_display()),
        ]

        if logged_in_info is not None:
            confirmed = "Yes" if logged_in_info["email_confirmed"] else "No"
            lines.append(
                line(
                    "Logged In As",
                    f"{logged_in_info['username']} "
                    f"({logged_in_info['email']})",
                )
            )
            lines.append(line("Email Confirmed", confirmed))
        else:
            lines.append(line("User Email", cd.get("email", "")))

        # Partnerships
        if cd.get("issue_type") == self.PARTNERSHIPS:
            lines.extend(
                [
                    line(
                        "Background",
                        self.label_for("partner_background", separator=", "),
                    ),
                    line(
                        "Background (other)",
                        cd.get("partner_background_other", ""),
                    ),
                    line("Current Work", cd.get("partner_current_work")),
                    line(
                        "Team Size", self.label_for("partner_team_size") or ""
                    ),
                    line("Founded Year", cd.get("partner_founded_year", "")),
                    line(
                        "Funding Total",
                        self.label_for("partner_funding_total") or "",
                    ),
                    line(
                        "Funding Stage",
                        self.label_for("partner_funding_stage") or "",
                    ),
                    line("Prior Outreach", cd.get("partner_prior_outreach")),
                    line("Ideal Outcome", cd.get("partner_ideal_outcome")),
                ]
            )

        # Technical
        elif cd.get("issue_type") in self.TECH_ISSUE_TYPES:
            tech_description = (cd.get("tech_description") or "-").replace(
                "\n", "<br>"
            )
            lines.extend(
                [
                    f"Technical Description:<br>{tech_description}",
                    line("Started At", cd.get("tech_started_at", "")),
                    line("Steps Tried", cd.get("tech_steps_tried", "")),
                    line("Links", cd.get("tech_links", "")),
                ]
            )

        message = (cd.get("message") or "").replace("\n", "<br>")
        lines.append(f"Message:<br>{message}")
        lines.append(line("Browser", user_agent))

        # Join fields with a blank line so each field reads as its own
        # paragraph in Zoho Desk.
        return "<br><br>".join(lines)

    def _get_email(self) -> str:
        """Return the email for the form"""
        if self.is_authenticated:
            return self.account_email
        return self.cleaned_data.get("email", "")

    def _is_sealing_order(self) -> bool:
        """Check if this submission should be treated as a sealing order."""
        cd = self.cleaned_data
        email = self._get_email()
        if email.lower().endswith(("@uscourts.gov", "@usdoj.gov")):
            return True
        if cd.get("issue_type") != self.REMOVAL_REQUEST:
            return False
        text = f"{cd.get('phone_number', '')} {cd.get('message', '')}"
        return bool(SEALING_KEYWORDS_REGEX.search(text))

    def get_zoho_request_type(self) -> str:
        """Return the Zoho Desk category for this submission.

        Submissions from government email domains (@uscourts.gov,
        @usdoj.gov) or Case Removal requests whose subject or message
        contain sealing-related keywords are recategorized as
        "Sealing Order".
        """
        if self._is_sealing_order():
            return "Sealing Order"
        return self.get_issue_type_display()

    def get_zoho_assignee_id(self) -> str:
        """Return the Zoho Desk agent ID for this submission's issue type.

        Returns empty string for unassigned tickets (sealing orders)
        and issue types without a configured agent.
        """
        if self._is_sealing_order():
            return ""
        return settings.ZOHO_DESK_AGENT_ASSIGNMENTS.get(
            self.cleaned_data.get("issue_type", ""), ""
        )

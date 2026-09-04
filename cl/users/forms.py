import re

from disposable_email_domains import blocklist
from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.forms import (
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from django.contrib.auth.validators import ASCIIUsernameValidator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import Value
from django.db.models.functions import Lower
from django.forms import ModelForm
from django.urls import reverse
from hcaptcha.fields import hCaptchaField
from localflavor.us.forms import USStateField, USZipCodeField
from localflavor.us.us_states import STATE_CHOICES

from cl.api.models import Webhook, WebhookEventType, WebhookVersions
from cl.lib.AuthenticationBackend import LOOKS_LIKE_EMAIL
from cl.lib.types import EmailType
from cl.users.models import UserProfile
from cl.users.utils import emails


# Many forms in here use unusual autocomplete attributes. These conform with
# https://html.spec.whatwg.org/multipage/forms.html#autofill, and enables them
# to be autofilled in various ways.
class ProfileForm(ModelForm):
    STATE_CHOICES = list(STATE_CHOICES)
    STATE_CHOICES.insert(0, ("", "---------"))
    state = USStateField(
        widget=forms.Select(
            choices=STATE_CHOICES,
            attrs={"class": "form-control", "autocomplete": "address-level1"},
        ),
        required=False,
    )
    zip_code = USZipCodeField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "postal-code"}
        ),
        required=False,
    )

    class Meta:
        model = UserProfile
        fields = (
            "employer",
            "address1",
            "address2",
            "city",
            "state",
            "zip_code",
            "is_tester",
            "docket_default_order_desc",
            "barmembership",
            "plaintext_preferred",
        )
        widgets = {
            "employer": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "organization",
                }
            ),
            "barmembership": forms.SelectMultiple(
                attrs={"size": "8", "class": "form-control"}
            ),
            "address1": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "address-line1",
                }
            ),
            "address2": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "address-line2",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "address-level2",
                }
            ),
        }


class CleanEmailMixin:
    def clean_email(self):
        email = self.cleaned_data.get("email")
        user_part, domain_part = email.rsplit("@", 1)
        blocklist.update(settings.BLOCKED_DOMAINS)
        if domain_part in blocklist:
            raise forms.ValidationError(
                f"{domain_part} is a blocked email provider",
                code="bad_email_domain",
            )
        return email


class UserForm(ModelForm, CleanEmailMixin):
    email = forms.EmailField(
        required=True,
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "email"}
        ),
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
        )
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "given-name",
                    "required": True,
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "family-name",
                    "required": True,
                }
            ),
        }


def validate_username_is_not_an_email(value: str) -> None:
    """Reject usernames shaped like an email address.

    ASCIIUsernameValidator permits "@" and ".", which makes somebody else's
    email address a registerable username. That interferes with signing in by
    email, and there is no non-revealing way to refuse only the addresses that
    have accounts: "that username is taken" would tell the registrant the
    address exists here. Refusing everything email-shaped is a flat rule about
    the format, so the response says nothing about what is in the database.

    The shape test is the same one the sign-in backend uses to decide whether
    an identifier is an address, so a username this accepts can never be
    mistaken for an address at sign-in. Something like "mal@ory" is fine; it
    has no domain.

    :param value: The submitted username.
    :return: None
    """
    if LOOKS_LIKE_EMAIL.match(value):
        raise ValidationError(
            "Usernames cannot be email addresses.",
            code="username_looks_like_email",
        )


class UserCreationFormExtended(UserCreationForm, CleanEmailMixin):
    """A bit of an unusual form because instead of creating it ourselves,
    we are overriding the one from Django. Thus, instead of declaring
    everything explicitly like we normally do, we just override the
    specific parts we want to, after calling the super class's __init__().

    Only one account may hold an email address, but the form never reports
    that an address is taken: "this email is already in use" would let anyone
    test whether an address has an account here. Instead the form validates
    normally and records the collision in ``email_taken``, and the view is
    expected to respond exactly as it would for a successful signup while
    emailing the address owner. Usernames get no such protection because they
    are already public in tag and prayer URLs, so username collisions are
    reported as errors like any other. What usernames may not do is look like
    an email address: see validate_username_is_not_an_email.

    This check belongs on the registration form only. UserForm, which shares
    CleanEmailMixin, must not get it until existing duplicate accounts have
    been cleaned up, or those users could no longer save their settings page.
    """

    email_taken: bool

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email_taken = False
        self.fields["username"].validators = [
            # Protect against homoglyph attacks
            ASCIIUsernameValidator(),
            validate_username_is_not_an_email,
        ]

        self.fields["username"].label = "User Name*"
        self.fields["email"].label = "Email Address*"
        self.fields["password1"].label = "Password*"
        self.fields["password2"].label = "Confirm Password*"
        self.fields["first_name"].label = "First Name*"
        self.fields["last_name"].label = "Last Name*"

        # Give all fields a form-control class.
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})

        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "username"}
        )
        self.fields["email"].required = True
        self.fields["email"].widget.attrs.update({"autocomplete": "email"})
        self.fields["password1"].widget.attrs.update(
            {"autocomplete": "new-password"}
        )
        self.fields["password2"].widget.attrs.update(
            {"autocomplete": "new-password"}
        )
        self.fields["first_name"].widget.attrs.update(
            {"autocomplete": "given-name", "required": True}
        )
        self.fields["last_name"].widget.attrs.update(
            {"autocomplete": "family-name", "required": True}
        )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
        )
        field_classes = {
            # Django's Meta maps this to UsernameField, whose to_python()
            # NFKC-normalizes before validators run. That would fold
            # lookalikes with an ASCII decomposition (fullwidth letters,
            # ligatures) into ASCII and let ASCIIUsernameValidator accept
            # them, so a plain CharField keeps them rejected instead.
            "username": forms.CharField,
        }

    def _email_is_taken(self, value: str) -> bool:
        """Report whether an account other than the bound instance holds
        `value` as its email address.

        Case is folded in SQL with Lower() on both sides rather than with
        str.lower() in Python. The two disagree on some non-ASCII input and the
        database collation is locale dependent, so folding in Python here while
        the LOWER(email) index folds in SQL could let a duplicate past the form
        only to fail at the index, or reject a legitimate address.

        The bound instance is excluded so that claiming a stub account, where
        the form is bound to the stub that already holds the address, is not
        mistaken for a duplicate.

        :param value: The string to compare against the email column.
        :return: True if some other account already has that address.
        """
        users = User.objects.annotate(email_lower=Lower("email")).filter(
            email_lower=Lower(Value(value))
        )
        if self.instance.pk:
            users = users.exclude(pk=self.instance.pk)
        return users.exists()

    def clean_email(self) -> str:
        """Run the shared email checks, then record whether another account
        already holds this address in ``email_taken``.

        A taken address is deliberately not a validation error. See the class
        docstring for why.
        """
        email = super().clean_email()
        self.email_taken = self._email_is_taken(email)
        return email

    def clean_first_name(self):
        first_name = self.cleaned_data.get("first_name")
        if re.search(r"""[!"#$%&()*+,./:;<=>?@[\]_{|}~]+""", first_name):
            raise forms.ValidationError(
                "First name must not contain any special characters."
            )
        return first_name


class EmailConfirmationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control input-lg",
                "placeholder": "Your Email Address",
                "autocomplete": "email",
                "autofocus": "on",
            }
        ),
        required=True,
    )


class OptInConsentForm(forms.Form):
    consent = forms.BooleanField(
        error_messages={
            "required": "To create a new account, you must agree below.",
        },
        required=True,
    )
    hcaptcha = hCaptchaField()


class PasswordConfirmForm(forms.Form):
    """Re-prompts the logged-in user for their password as a guard.

    Used by views that perform irreversible operations on the user's account
    (deleting it, rotating their API token, etc.).
    """

    password = forms.CharField(
        label="Confirm your password to continue...",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control input-lg",
                "placeholder": "Your password...",
                "autocomplete": "off",
                "autofocus": "on",
            },
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        """Set the request attribute for use by the clean method."""
        self.request = request
        super().__init__(*args, **kwargs)

    def clean_password(self) -> dict[str, str]:
        password = self.cleaned_data["password"]

        if password:
            # Pass the username, not the User, and check what comes back:
            # authenticate() also resolves email addresses, and this is a
            # re-prompt for *this* account, not an identity lookup. Without the
            # identity check, somebody whose username happened to be another
            # person's email address could clear this guard with that person's
            # password.
            user = authenticate(
                self.request,
                username=self.request.user.get_username(),
                password=password,
            )
            if user is None or user.pk != self.request.user.pk:
                raise ValidationError(
                    "Your password was invalid. Please try again."
                )

        return self.cleaned_data


class CustomPasswordChangeForm(PasswordChangeForm):
    """
    A form that lets a user change his/her password by entering
    their old password. Overrides Django default form to allow
    the customization of attributes.
    """

    old_password = forms.CharField(
        label="Old password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "current-password",
            }
        ),
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        ),
    )
    new_password2 = forms.CharField(
        label="New password confirmation",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        ),
    )


class CustomPasswordResetForm(PasswordResetForm):
    """A simple subclassing of a Django form in order to change class
    attributes.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].widget.attrs.update(
            {
                "class": "form-control input-lg",
                "placeholder": "Your Email Address",
                "autocomplete": "email",
            }
        )

    def save(self, *args, **kwargs) -> None:
        """Override the usual password form to send a message if we don't find
        any accounts
        """
        recipient_addr = self.cleaned_data["email"]
        users = self.get_users(recipient_addr)
        if not len(list(users)):
            email: EmailType = emails["no_account_found"]
            body = email["body"] % ("password reset", reverse("register"))
            send_mail(
                email["subject"], body, email["from_email"], [recipient_addr]
            )
        else:
            super().save(*args, **kwargs)


class CustomSetPasswordForm(SetPasswordForm):
    """A simple subclassing of a Django form in order to change class
    attributes.
    """

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)

        self.fields["new_password1"].widget.attrs.update(
            {
                "class": "form-control",
                "autocomplete": "new-password",
                "autofocus": "on",
            }
        )
        self.fields["new_password2"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "new-password"}
        )


class WebhookForm(ModelForm):
    def __init__(self, update=None, request_user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Determine the webhook type options to show accordingly.
        if update:
            # If we're updating an existing webhook, we only want to show the
            # webhook type that matches the current webhook.
            instance_type = [
                i
                for i in WebhookEventType.choices
                if i[0] == self.instance.event_type
            ]
            instance_version = [
                i
                for i in WebhookVersions.choices
                if i[0] == self.instance.version
            ]
            self.fields["event_type"].choices = instance_type
            self.fields["event_type"].widget.attrs["readonly"] = True
            self.fields["version"].choices = instance_version
            self.fields["version"].widget.attrs["readonly"] = True

        else:
            # If we're creating a new webhook, show the webhook type options
            # that are available for the user. One webhook for each event type
            # is allowed.
            webhooks = request_user.webhooks.all()
            used_version_types = [
                f"{w.event_type}_{w.version}" for w in webhooks
            ]
            available_type_choices = {
                w_type
                for w_type in WebhookEventType.choices
                for w_version in WebhookVersions.choices
                if f"{w_type[0]}_{w_version[0]}" not in used_version_types
            }
            self.fields["event_type"].choices = available_type_choices

    class Meta:
        model = Webhook
        fields = (
            "url",
            "event_type",
            "enabled",
            "version",
        )
        widgets = {
            "event_type": forms.Select(
                attrs={"class": "form-control"},
            ),
            "url": forms.TextInput(
                attrs={"class": "form-control"},
            ),
            "enabled": forms.CheckboxInput(
                attrs={"class": "webhook-checkbox"},
            ),
            "version": forms.Select(
                attrs={"class": "form-control"},
            ),
        }

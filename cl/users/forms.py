from disposable_email_domains import blocklist
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import (
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.forms import ModelForm
from django.urls import reverse
from hcaptcha.fields import hCaptchaField
from localflavor.us.forms import USStateField, USZipCodeField
from localflavor.us.us_states import STATE_CHOICES

from cl.api.models import Webhook, WebhookEventType
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


class UserForm(ModelForm):
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
                attrs={"class": "form-control", "autocomplete": "given-name"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "family-name"}
            ),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        user_part, domain_part = email.rsplit("@", 1)
        if domain_part in blocklist:
            raise forms.ValidationError(
                f"{domain_part} is a blocked email provider",
                code="bad_email_domain",
            )
        return email


class UserCreationFormExtended(UserCreationForm):
    """A bit of an unusual form because instead of creating it ourselves,
    we are overriding the one from Django. Thus, instead of declaring
    everything explicitly like we normally do, we just override the
    specific parts we want to, after calling the super class's __init__().
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
        )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        user_part, domain_part = email.rsplit("@", 1)
        if domain_part in blocklist:
            raise forms.ValidationError(
                f"{domain_part} is a blocked email provider",
                code="bad_email_domain",
            )
        return email


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


class AccountDeleteForm(forms.Form):
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
            user = authenticate(
                self.request, username=self.request.user, password=password
            )
            if user is None:
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
            self.fields["event_type"].choices = instance_type
            self.fields["event_type"].widget.attrs["readonly"] = True
        else:
            # If we're creating a new webhook, show the webhook type options
            # that are available for the user. One webhook for each event type
            # is allowed.
            webhooks = request_user.webhooks.all()
            used_types = [w.event_type for w in webhooks]
            available_choices = [
                i for i in WebhookEventType.choices if i[0] not in used_types
            ]
            self.fields["event_type"].choices = available_choices

    class Meta:
        model = Webhook
        fields = (
            "url",
            "event_type",
            "enabled",
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
        }

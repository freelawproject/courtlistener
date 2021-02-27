from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.urls import reverse


class ConfirmedEmailAuthenticationForm(AuthenticationForm):
    """Your average form, but with an additional tweak to ensure that only
    users with confirmed email addresses can log in.

    This is needed because we create stub accounts for people that donate and
    don't already have accounts. Without this check, people could sign up for
    accounts, log in, and see the donations of somebody that previously only
    had a stub account.
    """

    def __init__(self, *args, **kwargs) -> None:
        super(ConfirmedEmailAuthenticationForm, self).__init__(*args, **kwargs)

    def confirm_login_allowed(self, user: User) -> None:
        """Make sure the user is active and has a confirmed email address

        If the given user cannot log in, this method should raise a
        ``forms.ValidationError``.

        If the given user may log in, this method should return None.
        """
        if not user.is_active:
            raise forms.ValidationError(
                self.error_messages["inactive"],
                code="inactive",
            )

        if not user.profile.email_confirmed:
            raise forms.ValidationError(
                'Please <a href="%s">validate your email address</a> to '
                "log in." % reverse("email_confirmation_request")
            )

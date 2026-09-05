from typing import Any

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.forms import AuthenticationForm
from django.urls import reverse

from cl.lib.ratelimiter import (
    FAILED_LOGIN_LIMIT,
    count_login_attempt,
    reset_failed_login_count,
)


class ConfirmedEmailAuthenticationForm(AuthenticationForm):
    """Your average form, but with an additional tweak to ensure that only
    users with confirmed email addresses can log in.

    This is needed because we create stub accounts for people that donate and
    don't already have accounts. Without this check, people could sign up for
    accounts, log in, and see the donations of somebody that previously only
    had a stub account.

    It also throttles repeated failed sign-ins per submitted account
    identifier, so that credential stuffing can't work around the view's per-IP
    limit by spreading its guesses across many IPs.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        """Authenticate the user, counting attempts against the identifier.

        This is Django's own ``clean()`` with an attempt counter around the
        ``authenticate()`` call. Two things are worth knowing about it:

        Over-limit attempts get the *same* error as a wrong password. A distinct
        "too many attempts" message would tell an attacker they had found a live
        account, and would tell someone hammering a stranger's address that
        their nuisance had worked.

        An over-limit attempt is refused before ``authenticate()`` runs, so it
        costs no password hashes. It still counts, but counting doesn't extend
        the window: it ends a fixed time after the first attempt in it either
        way, so nobody can hold an account's owner out by continuing to guess.

        :return: The form's cleaned data.
        :raises forms.ValidationError: If the credentials are wrong, the
        identifier is over its limit, or the user isn't allowed to log in.
        """
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if username is None or not password:
            return self.cleaned_data

        # Count first, then check the password. One unit per POST, however many
        # candidate accounts the backend has to check the password against.
        if count_login_attempt(username) > FAILED_LOGIN_LIMIT:
            raise self.get_invalid_login_error()

        self.user_cache = authenticate(
            self.request, username=username, password=password
        )
        if self.user_cache is None:
            raise self.get_invalid_login_error()

        # The password was right, so this is the account's owner, even if
        # confirm_login_allowed() turns them away for an unconfirmed email.
        reset_failed_login_count(username)
        self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data

    def confirm_login_allowed(self, user: AbstractBaseUser) -> None:
        """Make sure the user is active and has a confirmed email address

        If the given user cannot log in, this method should raise a
        ``forms.ValidationError``.

        If the given user may log in, this method should return None.
        """
        if not user.is_active:  # type: ignore
            raise forms.ValidationError(
                self.error_messages["inactive"],
                code="inactive",
            )

        if not user.profile.email_confirmed:  # type: ignore
            raise forms.ValidationError(
                'Please <a href="{}">validate your email address</a> to '
                "log in.".format(reverse("email_confirmation_request"))
            )

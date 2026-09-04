import re

from django import forms
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import F, Value
from django.db.models.functions import Lower
from django.http import HttpRequest
from django.urls import reverse
from django.views.decorators.debug import sensitive_variables

# There can be many accounts for a given email address. To prevent
# DOS attacks, only check this many of them, then stop.
MAX_EMAIL_CANDIDATES = 3

# The loosest test that still tells an address from a username: something, an
# "@", and a domain with a dot in it. Anything stricter risks turning away an
# address that an older validator once let into auth_user.
LOOKS_LIKE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailOrUsernameModelBackend(ModelBackend):
    """Authenticate people by username or by email address.

    Django's ModelBackend resolves credentials with an exact match on
    ``username``, which fails the many people who only remember the address
    they signed up with. This backend tries the username first and falls back
    to accounts whose email address matches, so either identifier works.

    Callers use it through ``django.contrib.auth.authenticate()`` as usual;
    there is nothing CourtListener-specific in its interface. Two caveats:

    - An email address can match several accounts, because ``auth_user.email``
      is not unique. The submitted password disambiguates them, and only
      ``MAX_EMAIL_CANDIDATES`` of them are ever checked.
    - The user it returns is not necessarily allowed to log in. As with
      ModelBackend, deciding that is the form's job: an account with a correct
      password but an unconfirmed address comes back from here so that
      ``ConfirmedEmailAuthenticationForm`` can tell its owner to go confirm it.
    """

    @sensitive_variables("password")
    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs,
    ) -> User | None:
        """Find the account the submitted credentials belong to.

        The username is tried first and wins outright, because usernames may
        legally contain "@" and "." — ``victim@example.com`` is a registerable
        username. If a username matches but its password doesn't, we go on to
        the email candidates anyway, so registering a username equal to
        somebody's address can't lock that person out of email sign-in.

        :param request: The request being authenticated, if there is one.
        :param username: What the person typed in the identifier field: a
        username, an email address, or a User (whose str() is its username).
        :param password: The submitted password.
        :return: The matching User, or None if the credentials match nothing.
        """
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        # PasswordConfirmForm has historically passed a User here, relying on
        # User.__str__ returning the username.
        identifier = str(username)

        by_username = self._get_by_username(identifier)
        if (
            by_username is not None
            and by_username.check_password(password)
            and self.user_can_authenticate(by_username)
        ):
            return by_username

        candidates = self._get_email_candidates(
            identifier, exclude=by_username
        )
        if by_username is None and not candidates:
            # Nothing to check the password against. Run one throwaway hash
            # so that an address with no account takes as long as an address
            # with one. This is Django's own idiom, lifted verbatim from
            # ModelBackend.authenticate(); the User is never saved, so there
            # is no stored password here for validate_password() to check.
            # nosemgrep: python.django.security.audit.unvalidated-password.unvalidated-password
            User().set_password(password)
            return None

        # Candidates come back confirmed-first, then most recently used, so
        # the first one whose password matches is the best available: a
        # confirmed account if any matched, otherwise an unconfirmed one that
        # the form will turn into a "validate your email address" message.
        # Among confirmed accounts that means the most recently used one wins,
        # which is also the account the duplicate-account merge will keep, so
        # nothing changes for the user when their accounts are later merged.
        # Stopping at the first match also means no password is ever hashed
        # needlessly.
        for candidate in candidates:
            if candidate.check_password(
                password
            ) and self.user_can_authenticate(candidate):
                return candidate
        return None

    def _get_by_username(self, identifier: str) -> User | None:
        """Look an account up by exact username.

        :param identifier: The submitted identifier.
        :return: The account with that username, or None.
        """
        try:
            return User.objects.get_by_natural_key(identifier)
        except User.DoesNotExist:
            return None

    def _get_email_candidates(
        self, identifier: str, exclude: User | None
    ) -> list[User]:
        """Find the accounts an email address could refer to.

        Ordered by confirmed-then-most-recently-used and capped at
        MAX_EMAIL_CANDIDATES, because every account returned costs a password
        verification.

        Unconfirmed accounts stay in the list on purpose. Dropping them would
        turn "you never confirmed your address" into a generic "wrong
        credentials", which is less helpful than what people get today.

        :param identifier: The submitted identifier.
        :param exclude: An account already checked by username, if any, so we
        don't verify the same password against the same account twice.
        :return: The candidate accounts, confirmed ones first and, within
        that, most recently used first.
        """
        # Only an address has candidates, and the query is worth skipping for
        # anything else. This also keeps an empty identifier from matching
        # every account with a blank email address, a legal value on auth_user.
        if not LOOKS_LIKE_EMAIL.match(identifier):
            return []

        candidates = (
            User.objects.select_related("profile")
            # Match on LOWER(email) rather than __iexact, which compiles to
            # UPPER() and so can't use the auth_user_email_lower_idx index.
            # Fold the submitted value in SQL as well, so both sides use
            # Postgres's case rules: str.lower() and LOWER() disagree on some
            # non-ASCII characters.
            .alias(email_lower=Lower("email"))
            .filter(email_lower=Lower(Value(identifier)), is_active=True)
            # Stub accounts are placeholders for people who never signed up.
            # They have no usable password, so they can't match anyway, but
            # keeping them out of the list is one less thing to rely on.
            .exclude(profile__stub_account=True)
            # Confirmed accounts first, then most recently used. Confirmed
            # first is what keeps the cap below from being weaponised: anybody
            # can point an account at an address they don't control, but only
            # somebody who reads that address can confirm it, so planted
            # accounts can never crowd a confirmed one out of the candidates.
            .order_by(
                F("profile__email_confirmed").desc(nulls_last=True),
                F("last_login").desc(nulls_last=True),
            )
        )
        if exclude is not None:
            candidates = candidates.exclude(pk=exclude.pk)
        return list(candidates[:MAX_EMAIL_CANDIDATES])


class ConfirmedEmailAuthenticationForm(AuthenticationForm):
    """Your average form, but with an additional tweak to ensure that only
    users with confirmed email addresses can log in.

    This is needed because we create stub accounts for people that donate and
    don't already have accounts. Without this check, people could sign up for
    accounts, log in, and see the donations of somebody that previously only
    had a stub account.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

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

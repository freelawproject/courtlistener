from django import forms
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import F
from django.db.models.functions import Lower
from django.http import HttpRequest
from django.urls import reverse

# How many accounts sharing an email address we'll check a password against.
#
# Each candidate costs a full password verification — roughly 100ms of CPU — so
# an uncapped loop would let anybody who plants accounts on an address they
# control turn one login POST into as many hashes as they like. The cap also
# bounds a timing oracle: response time grows with the number of accounts on an
# address, and three is a small enough signal to accept.
#
# This is a cap on a transitional state. Once auth_user.email is unique, no
# address will have more than one account and the loop will only ever run once.
MAX_EMAIL_CANDIDATES = 3


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
        if by_username is not None and self._password_matches(
            by_username, password
        ):
            return by_username

        candidates = self._get_email_candidates(
            identifier, exclude=by_username
        )
        if by_username is None and not candidates:
            # Nothing to check the password against. Run one throwaway hash so
            # that an address with no account takes as long as an address with
            # one, as ModelBackend does.
            User().set_password(password)
            return None

        # Candidates are ordered by last_login descending, so the first match
        # is the account the person used most recently. That's also the account
        # the duplicate-account merge will keep, so the two agree and nothing
        # changes for the user when their accounts are later merged.
        unconfirmed_match = None
        for candidate in candidates:
            if not self._password_matches(candidate, password):
                continue
            if self._email_is_confirmed(candidate):
                return candidate
            # Hold on to it, but keep looking: a confirmed account signs its
            # owner in, while this one can only tell them to confirm their
            # address. Prefer the one that gets them in.
            unconfirmed_match = unconfirmed_match or candidate

        return unconfirmed_match

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

        Ordered by last_login descending and capped at MAX_EMAIL_CANDIDATES,
        because every account returned costs a password verification.

        Unconfirmed accounts stay in the list on purpose. Dropping them would
        turn "you never confirmed your address" into a generic "wrong
        credentials", which is less helpful than what people get today.

        :param identifier: The submitted identifier.
        :param exclude: An account already checked by username, if any, so we
        don't verify the same password against the same account twice.
        :return: The candidate accounts, most recently used first.
        """
        # An address always has an "@" in it, so an identifier without one has
        # no candidates to find, and the query is worth skipping. This also
        # keeps an empty identifier from matching every account with a blank
        # email address, which is a legal value on auth_user.
        if "@" not in identifier:
            return []

        candidates = (
            User.objects.select_related("profile")
            # Match on LOWER(email) rather than __iexact, which compiles to
            # UPPER() and so can't use the auth_user_email_lower_idx index.
            .alias(email_lower=Lower("email"))
            .filter(email_lower=identifier.lower(), is_active=True)
            # Stub accounts are placeholders for people who never signed up.
            # They have no usable password, so they can't match anyway, but
            # keeping them out of the list is one less thing to rely on.
            # exclude() leaves profile-less accounts in place; filtering on
            # profile__stub_account=False would drop them.
            .exclude(profile__stub_account=True)
            .order_by(F("last_login").desc(nulls_last=True))
        )
        if exclude is not None:
            candidates = candidates.exclude(pk=exclude.pk)
        return list(candidates[:MAX_EMAIL_CANDIDATES])

    def _password_matches(self, user: User, password: str) -> bool:
        """Check a password against one account.

        :param user: The account to check against.
        :param password: The submitted password.
        :return: Whether the password is right and the account may authenticate.
        """
        return bool(
            user.check_password(password) and self.user_can_authenticate(user)
        )

    def _email_is_confirmed(self, user: User) -> bool:
        """Report whether an account has confirmed its email address.

        :param user: The account to inspect.
        :return: True if it has a profile with a confirmed address.
        """
        # Accounts without a profile shouldn't exist, but a missing one here
        # would mean an unhandled exception on the sign-in page.
        profile = getattr(user, "profile", None)
        return bool(profile and profile.email_confirmed)


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

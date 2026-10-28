import base64
import json
import secrets
import time
from datetime import timedelta
from io import StringIO
from typing import Any, cast
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
import time_machine
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import RequestFactory, override_settings
from django.urls import (
    NoReverseMatch,
    URLPattern,
    URLResolver,
    get_resolver,
    reverse,
)
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from cl.api.authentication import ReplicaRoutingBasicAuthentication
from cl.api.models import APIThrottle, ThrottleType
from cl.api.utils import get_all_throttle_overrides
from cl.donate.api_views import MembershipWebhookViewSet
from cl.donate.factories import NeonMembershipFactory
from cl.donate.models import NeonMembershipLevel
from cl.lib.decorators import clear_tiered_cache
from cl.lib.url_utils import BASE_URL
from cl.sso.adapters import SocialAccountAdapter
from cl.sso.factories import (
    OrganizationDomainFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocialAppFactory,
    SSOConnectionFactory,
)
from cl.sso.linking import get_connection
from cl.sso.membership import EffectiveMembership, get_effective_membership
from cl.sso.models import (
    AuthEvent,
    AuthMethod,
    AuthOutcome,
    Enforcement,
    MembershipSource,
    OrganizationDomain,
    OrganizationMembership,
    SSOEmailException,
)
from cl.sso.policy import (
    RequirementReason,
    SSORequirement,
    requirement_for_user,
)
from cl.sso.sessions import SSO_AUTHENTICATED_AT_KEY, SSO_ORGANIZATION_KEY
from cl.sso.staff import build_staff_sso_report
from cl.sso.throttles import sync_user_throttles
from cl.tests.cases import SimpleTestCase, TestCase
from cl.users.factories import UserFactory, UserProfileWithParentsFactory
from cl.users.forms import (
    CustomPasswordResetForm,
    PasswordConfirmForm,
    UserCreationFormExtended,
    UserForm,
)
from cl.users.utils import delete_user_assets

ISSUER = "https://idp.acme.test"
CLIENT_ID = "courtlistener-test-client"
DOMAIN = "acme.test"


def _allauth_routes(
    patterns: list[URLPattern | URLResolver], prefix: str = ""
) -> dict[str, str]:
    """Map the name of every routed allauth view to its URL pattern.

    :param patterns: URL patterns to walk, recursing into includes.
    :param prefix: The pattern text of the enclosing includes.
    :return: {url name: full pattern} for views defined in allauth.
    """
    routes = {}
    for p in patterns:
        if isinstance(p, URLResolver):
            routes.update(
                _allauth_routes(p.url_patterns, prefix + str(p.pattern))
            )
            continue
        if p.callback.__module__.startswith("allauth."):
            routes[p.name or "<unnamed>"] = prefix + str(p.pattern)
    return routes


class AllauthRoutingTest(SimpleTestCase):
    """allauth must only add SSO URLs, never a second way to sign in."""

    def test_only_sso_views_are_routed(self) -> None:
        """Are allauth's password login, signup and reset pages unrouted?

        allauth.urls would mount those pages without CourtListener's rate
        limits and confirmed-email gate, so only these views may be routed.
        """
        routes = _allauth_routes(get_resolver().url_patterns)
        self.assertEqual(
            set(routes),
            {
                "socialaccount_login_cancelled",
                "socialaccount_login_error",
                "openid_connect_login",
                "openid_connect_callback",
                "saml_acs",
                "saml_finish_acs",
                "saml_sls",
                "saml_metadata",
                "saml_login",
            },
            msg=f"Unexpected allauth routes: {routes}",
        )

    def test_local_account_url_names_do_not_resolve(self) -> None:
        """Do allauth's local-account URL names fail to reverse?"""
        for name in (
            "account_signup",
            "account_email",
            "account_reset_password",
            "account_change_password",
            "account_set_password",
            "account_reauthenticate",
            "account_logout",
            "socialaccount_signup",
            "socialaccount_connections",
        ):
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_password_logins_use_only_courtlistener_backend(self) -> None:
        """Is EmailOrUsernameModelBackend still the only auth backend?

        allauth's adapter falls back to the first backend with get_user()
        when its own isn't listed, so SSO sessions don't need it, and leaving
        it out keeps it from checking passwords too.
        """
        self.assertEqual(
            settings.AUTHENTICATION_BACKENDS,
            ["cl.lib.AuthenticationBackend.EmailOrUsernameModelBackend"],
        )


class AllauthAliasTest(TestCase):
    """The allauth URL names its SSO flow redirects to."""

    def test_account_login_redirects_to_sign_in(self) -> None:
        """Does allauth's login URL name lead to CourtListener's sign-in?"""
        r = self.client.get(reverse("account_login"), {"next": "/alerts/"})
        self.assertRedirects(
            r,
            f"{reverse('sign-in')}?next=/alerts/",
            fetch_redirect_response=False,
        )

    def test_account_middleware_leaves_404s_alone(self) -> None:
        """Does a 404 under /sso/ stay a 404 instead of redirecting?"""
        r = self.client.get(f"{reverse('sso_start')}no-such-page/")
        self.assertEqual(r.status_code, 404)


class FakeResponse:
    """The parts of requests.Response that allauth reads."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.status_code = 200
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(data)
        self.content = self.text.encode()

    def json(self) -> dict[str, Any]:
        """Return the JSON body."""
        return self._data

    def raise_for_status(self) -> None:
        """Never raise; every fake response succeeds."""


class FakeIdP:
    """A stand-in for an organization's OIDC identity provider.

    Replaces the requests session allauth uses for discovery, the token
    exchange and userinfo, so a whole login runs without the network.
    """

    def __init__(self, sub: str, email: str) -> None:
        self.sub = sub
        self.email = email
        self.token_requests: list[dict[str, Any]] = []

    def __enter__(self) -> "FakeIdP":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        """Serve the discovery document and the userinfo endpoint."""
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return FakeResponse(
                {
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "userinfo_endpoint": f"{ISSUER}/userinfo",
                    "jwks_uri": f"{ISSUER}/jwks",
                    "token_endpoint_auth_methods_supported": [
                        "client_secret_post"
                    ],
                }
            )
        if url == f"{ISSUER}/userinfo":
            return FakeResponse(
                {
                    "sub": self.sub,
                    "email": self.email,
                    "email_verified": True,
                    "given_name": "Ada",
                    "family_name": "Lovelace",
                }
            )
        raise AssertionError(f"Unexpected GET to {url}")

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        """Serve the token endpoint, recording what was sent to it."""
        if url != f"{ISSUER}/token":
            raise AssertionError(f"Unexpected {method} to {url}")
        self.token_requests.append(kwargs.get("data") or {})
        now = int(time.time())
        # allauth skips the signature check for an id_token it fetched
        # directly over TLS (as the OIDC spec allows), so the key is unused.
        id_token = jwt.encode(
            {
                "iss": ISSUER,
                "aud": CLIENT_ID,
                "sub": self.sub,
                "email": self.email,
                "iat": now,
                "exp": now + 300,
            },
            secrets.token_hex(32),
            algorithm="HS256",
        )
        return FakeResponse(
            {
                "access_token": "fake-access-token",
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": id_token,
            }
        )


class SSOFixtureMixin:
    """An organization with a verified domain and an OIDC connection."""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        self.org = OrganizationFactory.create(
            name="Acme Law", slug="acme", session_max_age=3600
        )
        self.domain = OrganizationDomainFactory.create(
            organization=self.org, domain=DOMAIN
        )
        self.app = SocialAppFactory.create(
            provider_id="acme",
            client_id=CLIENT_ID,
            settings={"server_url": ISSUER},
        )
        self.connection = SSOConnectionFactory.create(
            organization=self.org, social_app=self.app
        )

    def require_sso(self) -> None:
        """Switch the organization's domain to required enforcement."""
        self.domain.enforcement = Enforcement.REQUIRED
        self.domain.save()


class OIDCLoginTest(SSOFixtureMixin, TestCase):
    """End-to-end OIDC logins against a fake IdP."""

    def setUp(self) -> None:
        super().setUp()
        neon = mock.patch("cl.sso.linking.create_neon_account")
        self.create_neon_account = neon.start()
        self.addCleanup(neon.stop)

    def _log_in_via_idp(self, idp: FakeIdP, next_url: str = "/alerts/"):
        """Run the browser side of an OIDC login and return the callback.

        On-commit callbacks (emails, throttle syncs) run as they would in
        production.

        :param idp: The fake IdP that answers allauth's back-channel calls.
        :param next_url: Where the person asked to end up.
        :return: The response from the OIDC callback view.
        """
        with (
            mock.patch.object(
                SocialAccountAdapter, "get_requests_session", return_value=idp
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            r = self.client.post(
                self.connection.get_login_url(), {"next": next_url}
            )
            self.assertEqual(r.status_code, 302)
            authorize = urlparse(r["Location"])
            self.assertEqual(
                f"{authorize.scheme}://{authorize.netloc}{authorize.path}",
                f"{ISSUER}/authorize",
            )
            query = parse_qs(authorize.query)
            self.assertEqual(query["client_id"], [CLIENT_ID])
            self.assertEqual(query["code_challenge_method"], ["S256"])
            return self.client.get(
                reverse(
                    "openid_connect_callback", kwargs={"provider_id": "acme"}
                ),
                {"code": "auth-code", "state": query["state"][0]},
            )

    def _confirmed_user(self, **kwargs: Any) -> User:
        """Make a confirmed account on the organization's domain."""
        kwargs.setdefault("user__email", f"ada@{DOMAIN}")
        return UserProfileWithParentsFactory.create(**kwargs).user

    def assertSignedInAs(self, user: User) -> None:
        """Assert the test client's session belongs to ``user``."""
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def assertNotSignedIn(self) -> None:
        """Assert the test client has no signed-in session."""
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_linked_identity_signs_in(self) -> None:
        """Does an IdP identity linked to an account sign that account in?"""
        user = self._confirmed_user()
        SocialAccount.objects.create(
            user=user, provider="acme", uid="acme-subject-1"
        )
        idp = FakeIdP(sub="acme-subject-1", email=user.email)

        r = self._log_in_via_idp(idp)

        self.assertRedirects(r, "/alerts/", fetch_redirect_response=False)
        self.assertSignedInAs(user)
        # The session belongs to CourtListener's backend, which restores it
        # on later requests.
        self.assertEqual(
            self.client.session["_auth_user_backend"],
            "cl.lib.AuthenticationBackend.EmailOrUsernameModelBackend",
        )
        self.assertIn("code_verifier", idp.token_requests[0])
        self.assertEqual(
            self.client.session[SSO_ORGANIZATION_KEY], self.org.pk
        )
        self.assertAlmostEqual(
            self.client.session.get_expiry_age(), 3600, delta=5
        )
        self.assertTrue(
            AuthEvent.objects.filter(
                user=user,
                method=AuthMethod.SSO,
                outcome=AuthOutcome.SUCCESS,
                connection=self.connection,
            ).exists()
        )
        # Already linked, so no "your account is now linked" email.
        self.assertEqual(len(mail.outbox), 0)

    def test_confirmed_account_is_linked(self) -> None:
        """Is a new identity linked to the confirmed account at its address?"""
        user = self._confirmed_user()

        r = self._log_in_via_idp(FakeIdP(sub="s-1", email=user.email))

        self.assertRedirects(r, "/alerts/", fetch_redirect_response=False)
        self.assertSignedInAs(user)
        self.assertTrue(
            SocialAccount.objects.filter(
                user=user, provider="acme", uid="s-1"
            ).exists()
        )
        membership = OrganizationMembership.objects.get(user=user)
        self.assertEqual(membership.source, MembershipSource.SSO)
        self.assertTrue(membership.has_seat)
        self.assertIsNotNone(membership.last_sso_login)
        self.assertTrue(
            AuthEvent.objects.filter(
                user=user, outcome=AuthOutcome.LINKED
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertIn("Acme Law", mail.outbox[0].subject)

    def test_session_end_is_fixed_at_sign_in(self) -> None:
        """Does activity after an SSO sign-in leave the session's end alone?"""
        user = self._confirmed_user()
        with time_machine.travel(timezone.now(), tick=False) as traveller:
            self._log_in_via_idp(FakeIdP(sub="s-1", email=user.email))
            expires = self.client.session.get_expiry_date()
            traveller.shift(timedelta(seconds=1000))
            self.client.get(reverse("show_results"))
            self.assertEqual(self.client.session.get_expiry_date(), expires)

    def test_seat_grants_api_throttles(self) -> None:
        """Does getting a seat give the organization's API rates?"""
        user = self._confirmed_user()

        self._log_in_via_idp(FakeIdP(sub="s-1", email=user.email))

        self.assertTrue(
            APIThrottle.objects.filter(
                user=user, source=APIThrottle.Source.MEMBERSHIP
            ).exists()
        )
        clear_tiered_cache()
        self.assertIn(
            user.username, get_all_throttle_overrides(ThrottleType.API)
        )

    def test_new_person_gets_an_account(self) -> None:
        """Does somebody new to CourtListener get a confirmed account?"""
        r = self._log_in_via_idp(FakeIdP(sub="s-1", email=f"new@{DOMAIN}"))

        self.assertRedirects(r, "/alerts/", fetch_redirect_response=False)
        user = User.objects.get(email=f"new@{DOMAIN}")
        self.assertSignedInAs(user)
        self.assertEqual(user.username, "new")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.profile.email_confirmed)
        self.assertEqual(user.first_name, "Ada")
        self.assertTrue(
            AuthEvent.objects.filter(
                user=user, outcome=AuthOutcome.CREATED
            ).exists()
        )
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user=user, organization=self.org
            ).exists()
        )

    def test_stub_account_is_upgraded(self) -> None:
        """Is a donor's stub account turned into the SSO account?"""
        stub = UserProfileWithParentsFactory.create(
            stub_account=True,
            email_confirmed=False,
            user__email=f"donor@{DOMAIN}",
            user__is_active=False,
        ).user
        users_before = User.objects.count()

        r = self._log_in_via_idp(FakeIdP(sub="s-1", email=stub.email))

        self.assertRedirects(r, "/alerts/", fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), users_before)
        stub.refresh_from_db()
        self.assertTrue(stub.is_active)
        self.assertFalse(stub.profile.stub_account)
        self.assertTrue(stub.profile.email_confirmed)
        self.assertSignedInAs(stub)

    def test_unverified_domain_is_refused(self) -> None:
        """Is an identity whose address isn't on a verified domain refused?

        Otherwise any IdP could claim anybody's address.
        """
        victim = self._confirmed_user(user__email="victim@elsewhere.test")

        r = self._log_in_via_idp(FakeIdP(sub="s-1", email=victim.email))

        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "verified domains", status_code=403)
        self.assertNotSignedIn()
        self.assertFalse(SocialAccount.objects.exists())
        self.assertTrue(
            AuthEvent.objects.filter(
                method=AuthMethod.SSO, outcome=AuthOutcome.REFUSED
            ).exists()
        )

    def test_unverified_domain_record_is_refused(self) -> None:
        """Is a domain that hasn't been verified refused too?"""
        self.domain.verified_at = None
        self.domain.save()
        user = self._confirmed_user()

        r = self._log_in_via_idp(FakeIdP(sub="s-1", email=user.email))

        self.assertEqual(r.status_code, 403)
        self.assertFalse(SocialAccount.objects.exists())

    def test_account_linked_to_another_subject_is_refused(self) -> None:
        """Is a reused address kept away from the previous holder's account?"""
        user = self._confirmed_user()
        SocialAccount.objects.create(
            user=user, provider="acme", uid="former-employee"
        )

        r = self._log_in_via_idp(FakeIdP(sub="new-hire", email=user.email))

        self.assertEqual(r.status_code, 403)
        self.assertNotSignedIn()
        self.assertFalse(SocialAccount.objects.filter(uid="new-hire").exists())

    def test_unconfirmed_accounts_are_not_linked(self) -> None:
        """Does an unconfirmed account at the address get passed over?

        It may have been planted by somebody else, so a new account is made
        and support is told about the duplicate.
        """
        planted = UserProfileWithParentsFactory.create(
            email_confirmed=False, user__email=f"ada@{DOMAIN}"
        ).user

        r = self._log_in_via_idp(FakeIdP(sub="s-1", email=planted.email))

        self.assertRedirects(r, "/alerts/", fetch_redirect_response=False)
        new_user = SocialAccount.objects.get(uid="s-1").user
        self.assertNotEqual(new_user.pk, planted.pk)
        self.assertSignedInAs(new_user)
        self.assertTrue(
            AuthEvent.objects.filter(outcome=AuthOutcome.FLAGGED).exists()
        )
        self.assertTrue(
            any("duplicate accounts" in m.subject for m in mail.outbox)
        )

    def test_duplicate_confirmed_accounts_are_flagged(self) -> None:
        """Is the most recently used account linked, and support told?"""
        older = self._confirmed_user(
            user__last_login=timezone.now() - timedelta(days=30)
        )
        newer = self._confirmed_user(user__last_login=timezone.now())

        self._log_in_via_idp(FakeIdP(sub="s-1", email=older.email))

        self.assertSignedInAs(newer)
        self.assertTrue(
            AuthEvent.objects.filter(
                user=newer, outcome=AuthOutcome.FLAGGED
            ).exists()
        )

    def test_seat_limit(self) -> None:
        """Does somebody past the seat limit join without benefits?"""
        self.org.seat_limit = 1
        self.org.save()
        OrganizationMembershipFactory.create(organization=self.org)
        user = self._confirmed_user()

        r = self._log_in_via_idp(FakeIdP(sub="s-1", email=user.email))

        self.assertRedirects(r, "/alerts/", fetch_redirect_response=False)
        membership = OrganizationMembership.objects.get(user=user)
        self.assertFalse(membership.has_seat)
        self.assertIsNone(get_effective_membership(user))
        self.assertTrue(any("seat" in m.subject.lower() for m in mail.outbox))

    def test_inactive_linked_account_is_refused(self) -> None:
        """Is a deactivated account kept out even with a linked identity?"""
        user = self._confirmed_user(user__is_active=False)
        SocialAccount.objects.create(
            user=user, provider="acme", uid="acme-subject-3"
        )

        r = self._log_in_via_idp(
            FakeIdP(sub="acme-subject-3", email=user.email)
        )

        self.assertEqual(r.status_code, 403)
        self.assertNotSignedIn()

    def test_disabled_connection_is_refused(self) -> None:
        """Does switching a connection off stop its logins?"""
        user = self._confirmed_user()
        SocialAccount.objects.create(user=user, provider="acme", uid="s-1")
        self.connection.is_enabled = False
        self.connection.save()

        r = self._log_in_via_idp(FakeIdP(sub="s-1", email=user.email))

        self.assertEqual(r.status_code, 403)
        self.assertNotSignedIn()


class EffectiveMembershipTest(TestCase):
    """Which membership's benefits a person gets."""

    def setUp(self) -> None:
        self.user = UserProfileWithParentsFactory.create().user
        self.org = OrganizationFactory.create(
            membership_level=NeonMembershipLevel.TIER_3
        )

    def test_free_user_has_none(self) -> None:
        """Does somebody with no membership get nothing?"""
        self.assertIsNone(get_effective_membership(self.user))
        self.assertFalse(self.user.profile.is_member)

    def test_organization_seat_counts(self) -> None:
        """Does a seat give the organization's level?"""
        OrganizationMembershipFactory.create(
            organization=self.org, user=self.user
        )
        membership = get_effective_membership(self.user)
        self.assertIsNotNone(membership)
        membership = cast(EffectiveMembership, membership)
        self.assertEqual(membership.level, NeonMembershipLevel.TIER_3)
        self.assertTrue(membership.is_organization)
        self.assertEqual(membership.neon_id, "")
        self.assertEqual(membership.level_display, "CL Membership - Tier 3")
        self.assertTrue(self.user.profile.is_member)

    def test_membership_without_seat_does_not_count(self) -> None:
        """Does joining without a seat give nothing?"""
        OrganizationMembershipFactory.create(
            organization=self.org, user=self.user, has_seat=False
        )
        self.assertIsNone(get_effective_membership(self.user))

    def test_neon_deletion_keeps_organization_rates(self) -> None:
        """Does losing a Neon membership fall back to the org's API rates?"""
        NeonMembershipFactory.create(
            user=self.user, level=NeonMembershipLevel.TIER_1, neon_id="99"
        )
        OrganizationMembershipFactory.create(
            organization=self.org, user=self.user
        )
        sync_user_throttles(self.user)

        MembershipWebhookViewSet._handle_membership_deletion(
            {"data": {"membership": {"membershipId": "99"}}}
        )

        self.assertTrue(
            APIThrottle.objects.filter(
                user=self.user, source=APIThrottle.Source.MEMBERSHIP
            ).exists()
        )

    def test_own_membership_wins(self) -> None:
        """Does a person's own Neon membership beat their organization's?"""
        NeonMembershipFactory.create(
            user=self.user, level=NeonMembershipLevel.TIER_1, neon_id="99"
        )
        OrganizationMembershipFactory.create(
            organization=self.org, user=self.user
        )
        membership = get_effective_membership(self.user)
        self.assertIsNotNone(membership)
        membership = cast(EffectiveMembership, membership)
        self.assertEqual(membership.level, NeonMembershipLevel.TIER_1)
        self.assertFalse(membership.is_organization)
        self.assertEqual(membership.neon_id, "99")

    def test_terminated_organization(self) -> None:
        """Do benefits last through the grace period, then stop?"""
        with time_machine.travel("2026-03-01 12:00:00-05:00", tick=False):
            self.org.termination_date = timezone.now()
            self.org.save()
            OrganizationMembershipFactory.create(
                organization=self.org, user=self.user
            )
            self.assertIsNotNone(get_effective_membership(self.user))
        with time_machine.travel("2026-06-01 12:00:00-05:00", tick=False):
            self.org.refresh_from_db()
            self.assertFalse(self.org.is_active)
            self.assertIsNone(get_effective_membership(self.user))

    def test_removing_membership_clears_throttles(self) -> None:
        """Does deleting an organization membership drop its API rates?"""
        membership = OrganizationMembershipFactory.create(
            organization=self.org, user=self.user
        )
        sync_user_throttles(self.user)
        self.assertTrue(APIThrottle.objects.filter(user=self.user).exists())

        membership.delete()

        self.assertFalse(
            APIThrottle.objects.filter(
                user=self.user, source=APIThrottle.Source.MEMBERSHIP
            ).exists()
        )


class EnforcementTest(SSOFixtureMixin, TestCase):
    """Password sign-in, registration and resets on SSO-required domains."""

    def setUp(self) -> None:
        super().setUp()
        self.user = UserProfileWithParentsFactory.create(
            user__email=f"ada@{DOMAIN}"
        ).user

    def _sign_in_with_password(self, user: User):
        """Post the sign-in form with the factory's password."""
        return self.client.post(
            reverse("sign-in"),
            {"username": user.username, "password": "password"},
        )

    def test_optional_domain_allows_passwords(self) -> None:
        """Can people still use passwords while SSO is only offered?"""
        self.domain.enforcement = Enforcement.OPTIONAL
        self.domain.save()
        self.assertIsNone(requirement_for_user(self.user))
        r = self._sign_in_with_password(self.user)
        self.assertEqual(r.status_code, 302)

    def test_password_sign_in_refused(self) -> None:
        """Is a correct password refused once SSO is required?"""
        self.require_sso()

        r = self._sign_in_with_password(self.user)

        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "requires single sign-on")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(
            AuthEvent.objects.filter(
                user=self.user,
                method=AuthMethod.PASSWORD,
                outcome=AuthOutcome.REFUSED,
            ).exists()
        )

    def test_email_exception_keeps_password(self) -> None:
        """Can a listed address keep signing in with a password?"""
        self.require_sso()
        SSOEmailException.objects.create(
            organization=self.org, email=self.user.email.upper()
        )
        r = self._sign_in_with_password(self.user)
        self.assertEqual(r.status_code, 302)

    def test_linked_account_elsewhere_still_required(self) -> None:
        """Can a linked person get around the policy by changing address?"""
        self.require_sso()
        OrganizationMembershipFactory.create(
            organization=self.org, user=self.user
        )
        self.user.email = "ada@personal.test"
        self.user.save()

        requirement = requirement_for_user(self.user)

        self.assertIsNotNone(requirement)
        self.assertEqual(
            cast(SSORequirement, requirement).reason, RequirementReason.LINKED
        )

    def test_staff_requirement(self) -> None:
        """Must staff use the staff organization's IdP when switched on?"""
        staff = UserProfileWithParentsFactory.create(
            user__is_staff=True, user__email="staff@free.law.test"
        ).user
        self.org.is_staff_organization = True
        self.org.save()

        with self.subTest("off"):
            self.assertIsNone(requirement_for_user(staff))
        with (
            self.subTest("on"),
            override_settings(SSO_REQUIRED_FOR_STAFF=True),
        ):
            requirement = requirement_for_user(staff)
            self.assertIsNotNone(requirement)
            self.assertEqual(
                cast(SSORequirement, requirement).reason,
                RequirementReason.STAFF,
            )

    def test_registration_refused(self) -> None:
        """Is a new password account on a required domain refused?"""
        self.require_sso()
        form = UserCreationFormExtended(
            {
                "username": "newperson",
                "email": f"new@{DOMAIN}",
                "password1": "a-long-Unusual-passw0rd",
                "password2": "a-long-Unusual-passw0rd",
            }
        )
        form.is_valid()
        self.assertIn("email", form.errors)
        self.assertIn("requires single sign-on", str(form.errors["email"]))

    def test_email_change_refused(self) -> None:
        """Can't somebody move their account onto a required domain?"""
        self.require_sso()
        outsider = UserProfileWithParentsFactory.create().user
        form = UserForm(
            {
                "email": f"outsider@{DOMAIN}",
                "first_name": "Out",
                "last_name": "Sider",
            },
            instance=outsider,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_email_change_allowed_for_linked_member(self) -> None:
        """Can a linked member switch between their organization's addresses?"""
        self.require_sso()
        OrganizationMembershipFactory.create(
            organization=self.org, user=self.user
        )
        form = UserForm(
            {
                "email": f"ada.lovelace@{DOMAIN}",
                "first_name": "Ada",
                "last_name": "Lovelace",
            },
            instance=self.user,
        )
        self.assertNotIn("email", form.errors)

    def test_password_reset_sends_sso_note(self) -> None:
        """Does a reset request get a "use SSO" note instead of a link?"""
        self.require_sso()
        form = CustomPasswordResetForm({"email": self.user.email})
        self.assertTrue(form.is_valid())

        form.save(
            domain_override="courtlistener.test",
            email_template_name="register/password_reset_email.html",
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("single sign-on", mail.outbox[0].body)
        self.assertNotIn("confirm-password/", mail.outbox[0].body)
        self.assertTrue(
            AuthEvent.objects.filter(
                method=AuthMethod.PASSWORD_RESET,
                outcome=AuthOutcome.REFUSED,
            ).exists()
        )

    def test_password_reset_for_email_exception(self) -> None:
        """Does an exempt account on a required domain still get a link?"""
        self.require_sso()
        SSOEmailException.objects.create(
            organization=self.org, email=self.user.email
        )
        form = CustomPasswordResetForm({"email": self.user.email})
        self.assertTrue(form.is_valid())
        form.save(
            domain_override="courtlistener.test",
            email_template_name="register/password_reset_email.html",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("single sign-on", mail.outbox[0].body)

    def test_password_reset_for_sso_created_account(self) -> None:
        """Can an SSO-made account set a password once SSO no longer applies?

        Support moves a departed employee's account to a personal address;
        the account has no password, so a reset is how they get one.
        """
        user = UserProfileWithParentsFactory.create(
            user__email="ada@personal.test"
        ).user
        user.set_unusable_password()
        user.save()
        AuthEvent.objects.create(
            user=user, method=AuthMethod.SSO, outcome=AuthOutcome.CREATED
        )
        bot = UserProfileWithParentsFactory.create(
            user__email="bot@personal.test"
        ).user
        bot.set_unusable_password()
        bot.save()

        for account, expect_link in ((user, True), (bot, False)):
            with self.subTest(account=account.email):
                mail.outbox = []
                form = CustomPasswordResetForm({"email": account.email})
                self.assertTrue(form.is_valid())
                form.save(
                    domain_override="courtlistener.test",
                    email_template_name="register/password_reset_email.html",
                )
                self.assertEqual(len(mail.outbox), 1)
                self.assertEqual(
                    "confirm-password/" in mail.outbox[0].body, expect_link
                )

    def test_basic_auth_refused(self) -> None:
        """Is HTTP Basic auth refused for SSO-required accounts?"""
        self.require_sso()
        credentials = base64.b64encode(
            f"{self.user.username}:password".encode()
        ).decode()
        request = Request(
            RequestFactory().get(
                "/api/rest/v4/", HTTP_AUTHORIZATION=f"Basic {credentials}"
            )
        )
        with self.assertRaises(AuthenticationFailed):
            ReplicaRoutingBasicAuthentication().authenticate(request)
        self.assertTrue(
            AuthEvent.objects.filter(
                method=AuthMethod.BASIC_AUTH, outcome=AuthOutcome.REFUSED
            ).exists()
        )

    def test_middleware_ends_password_sessions(self) -> None:
        """Is a password session ended once SSO becomes required?"""
        self.client.force_login(self.user)
        self.require_sso()

        r = self.client.get(reverse("view_settings"))

        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith(reverse("sso_start")))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_middleware_keeps_sso_sessions(self) -> None:
        """Does a session from the organization's IdP survive?"""
        self.require_sso()
        self.client.force_login(self.user)
        session = self.client.session
        session[SSO_ORGANIZATION_KEY] = self.org.pk
        session.save()

        r = self.client.get(reverse("view_settings"))

        self.assertEqual(r.status_code, 200)

    def test_failed_password_sign_in_is_logged(self) -> None:
        """Are wrong passwords recorded, without the identifier in clear?"""
        self.client.post(
            reverse("sign-in"),
            {"username": self.user.username, "password": "wrong"},
        )
        event = AuthEvent.objects.get(outcome=AuthOutcome.FAILURE)
        self.assertEqual(event.method, AuthMethod.PASSWORD)
        self.assertNotIn(self.user.username, event.identifier_hash)
        self.assertTrue(event.identifier_hash)


class PasswordConfirmFormTest(SSOFixtureMixin, TestCase):
    """Confirming sensitive actions without a password."""

    def setUp(self) -> None:
        super().setUp()
        self.user = UserProfileWithParentsFactory.create(
            user__email=f"ada@{DOMAIN}"
        ).user
        self.user.set_unusable_password()
        self.user.save()

    def _request(self, signed_in_ago: int | None):
        """Build a request from the SSO user, signed in some seconds ago."""
        request = RequestFactory().post(reverse("delete_account"))
        request.user = self.user
        request.session = {}  # type: ignore[assignment]
        if signed_in_ago is not None:
            request.session[SSO_AUTHENTICATED_AT_KEY] = (
                int(time.time()) - signed_in_ago
            )
        return request

    def test_recent_sso_login_confirms(self) -> None:
        """Does a recent IdP sign-in stand in for the password?"""
        form = PasswordConfirmForm(self._request(signed_in_ago=60), {})
        self.assertTrue(form.uses_sso)
        self.assertTrue(form.is_valid(), form.errors)

    def test_stale_sso_login_asks_to_sign_in_again(self) -> None:
        """Is somebody who signed in long ago sent back to their IdP?"""
        for ago in (None, 3600):
            with self.subTest(ago=ago):
                form = PasswordConfirmForm(self._request(ago), {})
                self.assertFalse(form.is_valid())
                self.assertIn("sign in again", str(form.errors))


class SSOStartViewTest(SSOFixtureMixin, TestCase):
    """The "sign in with SSO" page."""

    def test_get(self) -> None:
        """Does the page show the address form?"""
        r = self.client.get(reverse("sso_start"))
        self.assertContains(r, "Sign In with Single Sign-On")

    def test_sign_in_page_links_here(self) -> None:
        """Does the password sign-in page offer SSO?"""
        r = self.client.get(reverse("sign-in"))
        self.assertContains(r, reverse("sso_start"))

    def test_known_domain_continues_to_idp(self) -> None:
        """Does an SSO domain lead to a button that POSTs to the IdP login?"""
        self.domain.enforcement = Enforcement.OPTIONAL
        self.domain.save()
        r = self.client.post(
            reverse("sso_start"), {"email": f"ada@{DOMAIN}", "next": "/"}
        )
        self.assertTemplateUsed(r, "sso/continue.html")
        self.assertContains(r, self.connection.get_login_url())

    def test_domain_with_enforcement_off_is_not_offered(self) -> None:
        """Are domains still being tested kept off the page?"""
        r = self.client.post(reverse("sso_start"), {"email": f"ada@{DOMAIN}"})
        self.assertTemplateUsed(r, "sso/start.html")
        self.assertContains(r, "use single sign-on with CourtListener")

    def test_unknown_domain(self) -> None:
        """Is somebody whose domain doesn't use SSO pointed to passwords?"""
        r = self.client.post(
            reverse("sso_start"), {"email": "someone@nowhere.test"}
        )
        self.assertContains(r, "nowhere.test")


class AllauthPagePrivacyTest(SSOFixtureMixin, TestCase):
    """Pages that allauth's own views render."""

    def test_allauth_pages_are_private(self) -> None:
        """Are allauth's pages marked noindex, without the base warning?"""
        cases = [
            (self.connection.get_login_url(), 200),
            (reverse("socialaccount_login_cancelled"), 200),
            (reverse("socialaccount_login_error"), 401),
        ]
        for url, status in cases:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertContains(
                    r, 'name="robots" content="noindex', status_code=status
                )
                self.assertNotContains(
                    r, "did not supply the", status_code=status
                )

    def test_own_pages_keep_their_setting(self) -> None:
        """Do CourtListener's own pages keep the privacy they chose?"""
        r = self.client.get(reverse("sso_start"))

        self.assertNotContains(r, 'name="robots" content="noindex')


class TileSignInTest(SSOFixtureMixin, TestCase):
    """Sign-ins started by the IdP, such as a click on an Okta tile."""

    def setUp(self) -> None:
        super().setUp()
        neon = mock.patch("cl.sso.linking.create_neon_account")
        neon.start()
        self.addCleanup(neon.stop)
        self.user = UserProfileWithParentsFactory.create(
            user__email=f"ada@{DOMAIN}"
        ).user
        idp = mock.patch.object(
            SocialAccountAdapter,
            "get_requests_session",
            return_value=FakeIdP(sub="s-1", email=self.user.email),
        )
        idp.start()
        self.addCleanup(idp.stop)
        SocialAccount.objects.create(
            user=self.user, provider="acme", uid="s-1"
        )
        self.url = reverse("sso_oidc_initiate", kwargs={"provider_id": "acme"})

    def _click_tile(self, method: str = "get", **params: str):
        """Follow the IdP's link here, then complete the login at the IdP.

        :param method: "get" for a link, "post" for a form.
        :param params: The parameters the IdP sends; ``iss`` defaults to
        the connection's issuer.
        :return: The callback's response.
        """
        params.setdefault("iss", ISSUER)
        with self.captureOnCommitCallbacks(execute=True):
            r = getattr(self.client, method)(self.url, params)
            self.assertEqual(r.status_code, 302)
            authorize = urlparse(r["Location"])
            self.assertEqual(authorize.netloc, urlparse(ISSUER).netloc)
            self.query = parse_qs(authorize.query)
            return self.client.get(
                reverse(
                    "openid_connect_callback", kwargs={"provider_id": "acme"}
                ),
                {"code": "auth-code", "state": self.query["state"][0]},
            )

    def test_link_signs_in(self) -> None:
        """Does a plain link from the IdP sign the linked account in?"""
        r = self._click_tile()

        self.assertRedirects(
            r, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False
        )
        self.assertEqual(
            self.client.session["_auth_user_id"], str(self.user.pk)
        )
        self.assertEqual(self.query["code_challenge_method"], ["S256"])

    def test_form_post_signs_in(self) -> None:
        """Does a form the IdP posts here, without a CSRF token, work?"""
        self.client = self.client_class(enforce_csrf_checks=True)

        self._click_tile(method="post")

        self.assertEqual(
            self.client.session["_auth_user_id"], str(self.user.pk)
        )

    def test_target_link_uri(self) -> None:
        """Is a target on this site honored, and one elsewhere ignored?"""
        cases = [
            (f"{BASE_URL}/alerts/", "/alerts/"),
            ("/alerts/", "/alerts/"),
            ("https://evil.test/", settings.LOGIN_REDIRECT_URL),
        ]
        for target, expected in cases:
            with self.subTest(target=target):
                self.client.logout()
                r = self._click_tile(target_link_uri=target)
                self.assertRedirects(
                    r, expected, fetch_redirect_response=False
                )

    def test_login_hint_is_passed_on(self) -> None:
        """Is the IdP's login_hint sent back to it?"""
        self._click_tile(login_hint=self.user.email)

        self.assertEqual(self.query["login_hint"], [self.user.email])

    def test_issuer_forms(self) -> None:
        """Are trailing slashes and discovery URLs treated as the issuer?"""
        for iss in (f"{ISSUER}/", ISSUER):
            for server_url in (
                ISSUER,
                f"{ISSUER}/.well-known/openid-configuration",
            ):
                with self.subTest(iss=iss, server_url=server_url):
                    self.app.settings = {"server_url": server_url}
                    self.app.save()
                    r = self.client.get(self.url, {"iss": iss})
                    self.assertEqual(r.status_code, 302)

    def test_wrong_or_missing_issuer_is_refused(self) -> None:
        """Is a link that names a different IdP, or none, refused?"""
        for params in ({"iss": "https://other-idp.test"}, {}):
            with self.subTest(params=params):
                r = self.client.get(self.url, params)
                self.assertEqual(r.status_code, 400)
                self.assertTemplateUsed(r, "sso/error.html")
                self.assertContains(r, "initiate login URI", status_code=400)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_or_disabled_connection(self) -> None:
        """Do unknown, disabled and SAML connections 404?"""
        saml = SSOConnectionFactory.create(
            organization=self.org,
            social_app=SocialAppFactory.create(
                provider="saml", provider_id="acme-saml", client_id="acme"
            ),
        )
        missing = reverse("sso_oidc_initiate", kwargs={"provider_id": "nope"})
        saml_url = reverse(
            "sso_oidc_initiate", kwargs={"provider_id": saml.provider_id}
        )
        for url in (missing, saml_url):
            with self.subTest(url=url):
                r = self.client.get(url, {"iss": ISSUER})
                self.assertEqual(r.status_code, 404)

        self.connection.is_enabled = False
        self.connection.save()
        r = self.client.get(self.url, {"iss": ISSUER})
        self.assertEqual(r.status_code, 404)

    def test_idp_settings_list_the_urls(self) -> None:
        """Does the connection list the redirect and initiate login URIs?"""
        urls = self.connection.get_idp_settings()

        self.assertEqual(urls["Initiate login URI"], BASE_URL + self.url)
        self.assertEqual(
            urls["Sign-in redirect URI"],
            BASE_URL
            + reverse(
                "openid_connect_callback", kwargs={"provider_id": "acme"}
            ),
        )


class DomainTest(TestCase):
    """Domain records."""

    def test_free_email_domains_rejected(self) -> None:
        """Can't an organization claim gmail.com?"""
        domain = OrganizationDomain(
            organization=OrganizationFactory.create(), domain="Gmail.com"
        )
        with self.assertRaises(ValidationError):
            domain.full_clean()

    def test_enforcement_needs_verification(self) -> None:
        """Can't enforcement be turned on before the domain is verified?"""
        domain = OrganizationDomainFactory.build(
            organization=OrganizationFactory.create(),
            verified_at=None,
            enforcement=Enforcement.REQUIRED,
        )
        with self.assertRaises(ValidationError):
            domain.full_clean()

    def test_save_lowercases(self) -> None:
        """Are domains stored lowercased?"""
        domain = OrganizationDomainFactory.create(domain="Acme.TEST")
        self.assertEqual(domain.domain, "acme.test")


class SSOConnectionTest(TestCase):
    """Validation of IdP connections."""

    def test_saml_requires_signed_assertions(self) -> None:
        """Is a SAML app that accepts unsigned assertions rejected?"""
        for advanced, valid in (
            ({}, False),
            ({"want_assertion_signed": True}, True),
        ):
            with self.subTest(advanced=advanced):
                app = SocialAppFactory.create(
                    provider="saml",
                    settings={"idp": {}, "advanced": advanced},
                )
                connection = SSOConnectionFactory.build(
                    organization=OrganizationFactory.create(), social_app=app
                )
                if valid:
                    connection.clean()
                else:
                    with self.assertRaises(ValidationError):
                        connection.clean()

    def test_saml_refuses_idp_initiated_sign_in(self) -> None:
        """Is a SAML app that accepts IdP-started sign-ins rejected?"""
        for reject, valid in ((None, True), (True, True), (False, False)):
            advanced: dict[str, bool] = {"want_assertion_signed": True}
            if reject is not None:
                advanced["reject_idp_initiated_sso"] = reject
            with self.subTest(reject_idp_initiated_sso=reject):
                app = SocialAppFactory.create(
                    provider="saml",
                    settings={"idp": {}, "advanced": advanced},
                )
                connection = SSOConnectionFactory.build(
                    organization=OrganizationFactory.create(), social_app=app
                )
                if valid:
                    connection.clean()
                else:
                    with self.assertRaises(ValidationError):
                        connection.clean()

    def test_provider_id_required(self) -> None:
        """Must every connection have its own provider ID?"""
        connection = SSOConnectionFactory.build(
            organization=OrganizationFactory.create(),
            social_app=SocialAppFactory.create(provider_id=""),
        )
        with self.assertRaises(ValidationError):
            connection.clean()

    def test_shared_provider_id_rejected(self) -> None:
        """Is a provider ID that another SocialApp uses rejected?"""
        SocialAppFactory.create(provider_id="shared")
        connection = SSOConnectionFactory.build(
            organization=OrganizationFactory.create(),
            social_app=SocialAppFactory.create(provider_id="shared"),
        )
        with self.assertRaises(ValidationError):
            connection.clean()

    def test_shared_provider_id_matches_no_connection(self) -> None:
        """Is a login refused when two connections share a provider ID?"""
        sociallogin = cast(
            SocialLogin, mock.Mock(account=mock.Mock(provider="shared"))
        )
        SSOConnectionFactory.create(
            social_app=SocialAppFactory.create(provider_id="shared")
        )
        self.assertIsNotNone(get_connection(sociallogin))

        SSOConnectionFactory.create(
            social_app=SocialAppFactory.create(provider_id="shared")
        )
        self.assertIsNone(get_connection(sociallogin))


class StaffReportTest(TestCase):
    """The staff-MFA report and its management command."""

    def test_unlinked_staff_reported(self) -> None:
        """Is a staff account that can't sign in through the IdP flagged?"""
        org = OrganizationFactory.create(is_staff_organization=True)
        SSOConnectionFactory.create(organization=org)
        staff = UserProfileWithParentsFactory.create(user__is_staff=True).user

        report = build_staff_sso_report()

        self.assertIn(staff, report.unlinked)
        self.assertTrue(any("aren't linked" in p for p in report.problems))

    def test_linked_staff_not_reported(self) -> None:
        """Is a linked staff account left out of the problems?"""
        org = OrganizationFactory.create(is_staff_organization=True)
        connection = SSOConnectionFactory.create(organization=org)
        staff = UserProfileWithParentsFactory.create(user__is_staff=True).user
        SocialAccount.objects.create(
            user=staff, provider=connection.provider_id, uid="flp-1"
        )
        report = build_staff_sso_report()
        self.assertNotIn(staff, report.unlinked)

    def test_command_runs(self) -> None:
        """Does check_staff_sso print the report?"""
        out = StringIO()
        call_command("check_staff_sso", stdout=out)
        self.assertIn("staff organization", out.getvalue())


class NotifyDomainUsersTest(SSOFixtureMixin, TestCase):
    """The notify_sso_domain_users command."""

    def test_dry_run_then_send(self) -> None:
        """Does it list people first and only email them with --send?"""
        user = UserProfileWithParentsFactory.create(
            user__email=f"ada@{DOMAIN}"
        ).user
        UserProfileWithParentsFactory.create(user__email="bob@other.test")

        out = StringIO()
        call_command("notify_sso_domain_users", DOMAIN, stdout=out)
        self.assertIn("1 confirmed account(s)", out.getvalue())
        self.assertEqual(len(mail.outbox), 0)

        call_command("notify_sso_domain_users", DOMAIN, "--send", stdout=out)
        self.assertEqual([m.to for m in mail.outbox], [[user.email]])


class AccountDeletionTest(SSOFixtureMixin, TestCase):
    """Deleting an account removes its SSO links."""

    def test_delete_user_assets(self) -> None:
        """Are the identity link and organization membership deleted?"""
        user = UserProfileWithParentsFactory.create().user
        SocialAccount.objects.create(user=user, provider="acme", uid="s-1")
        OrganizationMembershipFactory.create(organization=self.org, user=user)

        delete_user_assets(user)

        self.assertFalse(SocialAccount.objects.filter(user=user).exists())
        self.assertFalse(
            OrganizationMembership.objects.filter(user=user).exists()
        )

    def test_delete_leaves_no_membership_throttles(self) -> None:
        """Are API throttles gone for a member who also holds a seat?"""
        user = UserProfileWithParentsFactory.create().user
        NeonMembershipFactory.create(
            user=user, level=NeonMembershipLevel.TIER_1
        )
        OrganizationMembershipFactory.create(organization=self.org, user=user)
        sync_user_throttles(user)

        delete_user_assets(user)

        self.assertFalse(APIThrottle.objects.filter(user=user).exists())


class AdminTest(SSOFixtureMixin, TestCase):
    """The organization admin's actions."""

    def test_connection_shows_idp_urls(self) -> None:
        """Does the organization page list each connection's IdP URLs?"""
        admin_user = UserFactory.create(is_staff=True, is_superuser=True)
        self.client.force_login(admin_user)

        r = self.client.get(
            reverse("admin:sso_organization_change", args=[self.org.pk])
        )

        self.assertContains(
            r, self.connection.get_idp_settings()["Initiate login URI"]
        )

    def test_export_members(self) -> None:
        """Does the CSV export list the organization's members?"""
        admin_user = UserFactory.create(is_staff=True, is_superuser=True)
        member = OrganizationMembershipFactory.create(organization=self.org)
        self.client.force_login(admin_user)

        r = self.client.post(
            reverse("admin:sso_organization_changelist"),
            {"action": "export_members", "_selected_action": [self.org.pk]},
        )

        self.assertEqual(r["Content-Type"], "text/csv")
        self.assertIn(member.user.username, r.content.decode())

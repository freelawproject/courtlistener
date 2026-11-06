import base64
import hashlib
import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from oauth2_provider.models import (
    get_access_token_model,
    get_application_model,
    get_grant_model,
    get_refresh_token_model,
    set_token_value,
)
from rest_framework.authtoken.models import Token
from waffle.testutils import override_switch

from cl.oauth.factories import ApplicationFactory
from cl.oauth.validators import DCR_REFRESH_SWITCH
from cl.tests.cases import APITestCase, TestCase
from cl.tests.utils import parse_csp
from cl.users.factories import UserFactory, UserProfileWithParentsFactory

Application = get_application_model()
Grant = get_grant_model()
AccessToken = get_access_token_model()
RefreshToken = get_refresh_token_model()


class OAuthMetadataTest(APITestCase):
    """Tests for the RFC 8414 metadata endpoint."""

    def setUp(self):
        super().setUp()
        self.url = reverse("oauth2_metadata")

    def test_metadata_shape(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Required RFC 8414 fields.
        for field in (
            "issuer",
            "authorization_endpoint",
            "token_endpoint",
            "response_types_supported",
        ):
            self.assertIn(field, body)
        # MCP-specific expectations.
        self.assertIn("S256", body["code_challenge_methods_supported"])
        self.assertIn("authorization_code", body["grant_types_supported"])
        self.assertEqual(body["response_types_supported"], ["code"])
        # RFC 9207: we append ``iss`` to authorization responses, so say so.
        self.assertIs(
            body["authorization_response_iss_parameter_supported"], True
        )
        # Endpoints should be absolute URLs that share an origin with
        # the issuer.
        self.assertTrue(
            body["authorization_endpoint"].startswith(body["issuer"])
        )
        self.assertTrue(body["token_endpoint"].startswith(body["issuer"]))
        # Dynamic Client Registration is retired, so nothing to advertise.
        self.assertNotIn("registration_endpoint", body)

    def test_registration_endpoint_is_gone(self):
        for path in ("/o/register/", "/o/register/some-client-id/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path).status_code, 404)

    def test_scopes_supported_excludes_oidc_scopes_when_oidc_disabled(self):
        with patch.dict(settings.OAUTH2_PROVIDER, {"OIDC_ENABLED": False}):
            resp = self.client.get(self.url)
        self.assertEqual(resp.json()["scopes_supported"], ["api", "wiki"])

    def test_scopes_supported_lists_every_scope_when_oidc_enabled(self):
        with patch.dict(settings.OAUTH2_PROVIDER, {"OIDC_ENABLED": True}):
            resp = self.client.get(self.url)
        self.assertEqual(
            resp.json()["scopes_supported"],
            ["api", "wiki", "openid", "email", "profile"],
        )


class ApplicationRedirectUriPolicyTest(TestCase):
    """Non-DCR code paths (admin, shell, direct ORM) must be held to the
    same loopback-only policy for http:// redirect URIs that the DCR
    serializer enforces. This exercises the pre_save signal in
    ``cl.oauth.signals``.
    """

    def _make_app(self, redirect_uris: str) -> Application:
        return Application(
            name="t",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=redirect_uris,
        )

    def test_https_allowed(self):
        self._make_app("https://mcp.example.com/cb").save()

    def test_http_loopback_allowed(self):
        self._make_app("http://127.0.0.1:8080/cb").save()

    def test_http_non_loopback_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            self._make_app("http://attacker.example.com/cb").save()
        self.assertIn("loopback", str(cm.exception))

    def test_unsupported_scheme_rejected(self):
        with self.assertRaises(ValidationError):
            self._make_app("javascript:alert(1)").save()


def s256_challenge(verifier: str) -> str:
    """Return the RFC 7636 S256 code_challenge for ``verifier``."""
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )


class PKCEMethodEnforcementTest(TestCase):
    """Only S256 PKCE is accepted, as the RFC 8414 metadata promises.

    oauthlib defaults an absent ``code_challenge_method`` to ``"plain"``, so
    an omitted method has to be refused as well as an explicit ``plain``.
    django-oauth-toolkit enforces this through the RFC 9700
    ``COMPLIANT_BCP_RFC9700_PKCE_METHOD`` gate when the authorization code
    is minted, so the consent screen renders but approving it fails.
    """

    REDIRECT_URI = "https://mcp.example.com/callback"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.application = ApplicationFactory(
            client_type=Application.CLIENT_PUBLIC,
            redirect_uris=cls.REDIRECT_URI,
        )

    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.user)

    def _approve(self, code_challenge_method: str | None):
        """Run the consent screen for a client using ``code_challenge_method``.

        Returns the response to the approval POST. ``None`` omits the
        parameter entirely.
        """
        verifier = "a" * 64
        params = {
            "response_type": "code",
            "client_id": self.application.client_id,
            "redirect_uri": self.REDIRECT_URI,
            "scope": "api",
            "state": "xyz",
            "code_challenge": (
                s256_challenge(verifier)
                if code_challenge_method == "S256"
                else verifier
            ),
        }
        if code_challenge_method is not None:
            params["code_challenge_method"] = code_challenge_method
        url = reverse("oauth2_provider:authorize")
        consent = self.client.get(url, params)
        self.assertEqual(consent.status_code, 200, consent.content)
        return self.client.post(url, {**params, "allow": "Authorize"})

    def test_s256_is_accepted(self):
        r = self._approve("S256")
        self.assertEqual(r.status_code, 302)
        self.assertIn("code=", r["Location"])
        self.assertEqual(Grant.objects.count(), 1)

    def test_weak_methods_are_rejected(self):
        for method in ("plain", None):
            with self.subTest(code_challenge_method=method):
                r = self._approve(method)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r["Location"].startswith(self.REDIRECT_URI))
                self.assertIn("error=invalid_request", r["Location"])
                self.assertNotIn("code=", r["Location"])
                self.assertEqual(Grant.objects.count(), 0)


class AudienceBoundTokenTest(APITestCase):
    """The REST API honors audience-bound tokens, whatever the audience.

    ``RESOURCE_SERVER_TOKEN_RESOURCE_VALIDATOR`` is ``None`` so the MCP
    server keeps working: the client binds its token to the MCP server's URL
    and the MCP server forwards it here. This guards against the toolkit's
    default validator being restored by accident.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.application = ApplicationFactory()

    def _token(self, resource: list[str]) -> str:
        raw = f"tok-{len(resource)}-{'-'.join(resource)}"
        token = AccessToken(
            user=self.user,
            application=self.application,
            scope="api",
            expires=now() + timedelta(hours=1),
            resource=resource,
        )
        set_token_value(token, raw)
        token.save()
        return raw

    def test_audiences(self):
        url = reverse("alert-list", kwargs={"version": "v4"})
        for label, resource in (
            ("unrestricted", []),
            ("hosted MCP server", ["https://mcp.courtlistener.com/"]),
            ("self-hosted MCP server", ["https://mcp.example.org/"]),
        ):
            with self.subTest(label):
                r = self.client.get(
                    url, HTTP_AUTHORIZATION=f"Bearer {self._token(resource)}"
                )
                self.assertEqual(r.status_code, 200, r.content)


class ApiScopeEnforcementTest(APITestCase):
    """The REST API accepts OAuth tokens only when they carry ``api``.

    Identity and wiki tokens are rejected with 403, the RFC 6750
    ``insufficient_scope`` status. API keys are unaffected.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.application = ApplicationFactory()
        cls.url = reverse("alert-list", kwargs={"version": "v4"})

    def _token(self, scope: str) -> str:
        raw = f"tok-{scope.replace(' ', '-')}"
        token = AccessToken(
            user=self.user,
            application=self.application,
            scope=scope,
            expires=now() + timedelta(hours=1),
        )
        set_token_value(token, raw)
        token.save()
        return raw

    def test_api_scope_is_accepted(self):
        for scope in ("api", "openid api wiki"):
            with self.subTest(scope=scope):
                r = self.client.get(
                    self.url, HTTP_AUTHORIZATION=f"Bearer {self._token(scope)}"
                )
                self.assertEqual(r.status_code, 200, r.content)

    def test_tokens_without_api_scope_are_refused(self):
        for scope in ("openid", "openid email profile", "openid wiki"):
            with self.subTest(scope=scope):
                r = self.client.get(
                    self.url, HTTP_AUTHORIZATION=f"Bearer {self._token(scope)}"
                )
                self.assertEqual(r.status_code, 403, r.content)
                self.assertIn("api scope", r.json()["detail"])
                self.assertEqual(
                    r["WWW-Authenticate"],
                    'Bearer realm="api", error="insufficient_scope", '
                    'scope="api"',
                )

    def test_api_keys_are_unaffected(self):
        key, _ = Token.objects.get_or_create(user=self.user)
        r = self.client.get(self.url, HTTP_AUTHORIZATION=f"Token {key.key}")
        self.assertEqual(r.status_code, 200, r.content)


class AuthorizeViewCSPTest(TestCase):
    """The authorize view has to opt out of the site-wide ``form-action``.

    Approving a client POSTs to us and then redirects to the client's
    ``redirect_uri``, which is by definition another origin. Chrome enforces
    ``form-action`` against that redirect, so leaving the site-wide policy in
    place would break the whole flow in some browsers. ``cl.oauth.urls`` wraps
    the view in ``csp_override`` to drop the directive; these tests hold that
    exemption to the one view that needs it.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.application = Application.objects.create(
            name="Example MCP Client",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://mcp.example.com/callback",
        )

    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.user)

    def _get_authorize_page(self):
        """Requests the consent screen the way a real client would."""
        verifier = "a" * 64
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            )
            .decode()
            .rstrip("=")
        )
        return self.client.get(
            reverse("oauth2_provider:authorize"),
            {
                "response_type": "code",
                "client_id": self.application.client_id,
                "redirect_uri": "https://mcp.example.com/callback",
                "scope": "api",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )

    def test_authorize_page_omits_form_action(self):
        """The consent screen ships without the directive that breaks it."""
        r = self._get_authorize_page()
        self.assertEqual(r.status_code, 200, r.content)
        directives = parse_csp(r)
        self.assertNotIn("form-action", directives)

    def test_authorize_page_keeps_the_rest_of_the_policy(self):
        """Only form-action is dropped.

        ``csp_override`` replaces the policy wholesale rather than editing it,
        so a stale copy of the settings would silently weaken this page. Spot
        check a few directives against the live setting to catch that.
        """
        r = self._get_authorize_page()
        directives = parse_csp(r)
        self.assertEqual(directives["base-uri"], ["'self'"])
        self.assertEqual(
            directives["default-src"], settings.SECURE_CSP["default-src"]
        )
        self.assertEqual(
            set(directives) | {"form-action"},
            {
                directive
                for directive, sources in settings.SECURE_CSP.items()
                if sources is not False
            },
        )

    def test_other_oauth_pages_keep_form_action(self):
        """The exemption doesn't leak to the URLs mounted beside it."""
        r = self.client.get(reverse("oauth2_metadata"))
        self.assertEqual(parse_csp(r)["form-action"], ["'self'"])


class CleanOAuthTablesCommandTest(TestCase):
    """The command clears expired grants and tokens and leaves every
    application alone, authorized or not."""

    def test_clears_expired_grants_and_keeps_applications(self):
        """Expired grants go; a never-authorized application stays."""
        app = ApplicationFactory(name="never authorized")
        expired_grant = Grant.objects.create(
            user=UserFactory(),
            code="expired-code",
            application=app,
            expires=now() - timedelta(hours=1),
            redirect_uri="https://client.example.com/callback",
        )
        call_command("clean_oauth_tables")
        self.assertFalse(Grant.objects.filter(pk=expired_grant.pk).exists())
        self.assertTrue(Application.objects.filter(pk=app.pk).exists())


class RegistrationSourceBackfillTest(TestCase):
    """Our data migration labels pre-3.4 DCR applications as ``dcr``."""

    def test_only_ownerless_consent_requiring_apps_are_relabeled(self):
        manual = Application.RegistrationSource.MANUAL
        dcr = ApplicationFactory(registration_source=manual)
        owned = ApplicationFactory(
            user=UserFactory(), registration_source=manual
        )
        in_house = ApplicationFactory(
            skip_authorization=True, registration_source=manual
        )
        migration = importlib.import_module(
            "cl.oauth.migrations.0001_backfill_registration_source"
        )
        migration.label_dcr_applications(
            apps, SimpleNamespace(connection=connection)
        )
        for app, expected in (
            (dcr, Application.RegistrationSource.DCR),
            (owned, manual),
            (in_house, manual),
        ):
            with self.subTest(app=app.name):
                app.refresh_from_db()
                self.assertEqual(app.registration_source, expected)


@override_settings(
    OAUTH2_PROVIDER={**settings.OAUTH2_PROVIDER, "OIDC_ENABLED": True}
)
class OIDCClaimsTest(APITestCase):
    """Userinfo and discovery expose the validator's claims by scope."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.profile = UserProfileWithParentsFactory(
            user__first_name="Ada", user__last_name="Lovelace"
        )
        cls.user = cls.profile.user
        cls.application = ApplicationFactory()

    def _userinfo(self, user, scope: str) -> dict:
        """Mint a token with *scope* for *user* and fetch their claims."""
        raw = f"tok-{user.pk}-{scope.replace(' ', '-')}"
        token = AccessToken(
            user=user,
            application=self.application,
            scope=scope,
            expires=now() + timedelta(hours=1),
        )
        set_token_value(token, raw)
        token.save()
        resp = self.client.get(
            reverse("oauth2_provider:user-info"),
            HTTP_AUTHORIZATION=f"Bearer {raw}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_claims_follow_granted_scopes(self):
        profile_claims = {"name", "given_name", "family_name"}
        email_claims = {"email", "email_verified"}
        for scope, expected in (
            ("openid", set()),
            ("openid email", email_claims),
            ("openid profile", profile_claims),
            ("openid email profile", email_claims | profile_claims),
            ("openid api wiki", set()),
        ):
            with self.subTest(scope=scope):
                claims = self._userinfo(self.user, scope)
                self.assertEqual(set(claims), {"sub"} | expected)

    def test_claim_values(self):
        claims = self._userinfo(self.user, "openid email profile")
        self.assertEqual(claims["sub"], str(self.user.pk))
        self.assertEqual(claims["email"], self.user.email)
        self.assertIs(claims["email_verified"], True)
        self.assertEqual(claims["name"], "Ada Lovelace")
        self.assertEqual(claims["given_name"], "Ada")
        self.assertEqual(claims["family_name"], "Lovelace")

    def test_unconfirmed_email_is_not_verified(self):
        profile = UserProfileWithParentsFactory(email_confirmed=False)
        claims = self._userinfo(profile.user, "openid email")
        self.assertEqual(claims["email"], profile.user.email)
        self.assertIs(claims["email_verified"], False)

    def test_blank_email_omits_email_verified(self):
        profile = UserProfileWithParentsFactory(
            user__email="", email_confirmed=True
        )
        claims = self._userinfo(profile.user, "openid email")
        self.assertEqual(set(claims), {"sub"})

    def test_empty_name_claims_are_omitted(self):
        profile = UserProfileWithParentsFactory(
            user__first_name="", user__last_name=""
        )
        claims = self._userinfo(profile.user, "openid profile")
        self.assertEqual(set(claims), {"sub"})

    def test_discovery_advertises_claims_and_scopes(self):
        resp = self.client.get(
            reverse("oauth2_provider:oidc-connect-discovery-info")
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        for claim in (
            "sub",
            "email",
            "email_verified",
            "name",
            "given_name",
            "family_name",
        ):
            with self.subTest(claim=claim):
                self.assertIn(claim, body["claims_supported"])
        for scope in ("api", "wiki", "openid", "email", "profile"):
            with self.subTest(scope=scope):
                self.assertIn(scope, body["scopes_supported"])


class IntrospectionSubTest(APITestCase):
    """Introspection includes ``sub`` matching the OIDC subject."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.application = ApplicationFactory(client_secret="wiki-secret")
        cls.url = reverse("oauth2_provider:introspect")

    def _introspect(self, token_value: str) -> dict:
        creds = base64.b64encode(
            f"{self.application.client_id}:wiki-secret".encode()
        ).decode()
        resp = self.client.post(
            self.url,
            {"token": token_value},
            HTTP_AUTHORIZATION=f"Basic {creds}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_active_token_includes_sub(self):
        token = AccessToken(
            user=self.user,
            application=self.application,
            scope="openid api wiki",
            expires=now() + timedelta(hours=1),
            resource=["https://wiki.free.law/"],
        )
        set_token_value(token, "introspect-me")
        token.save()
        data = self._introspect("introspect-me")
        self.assertIs(data["active"], True)
        self.assertEqual(data["sub"], str(self.user.pk))
        self.assertEqual(data["username"], self.user.username)
        self.assertEqual(data["scope"], "openid api wiki")
        self.assertEqual(data["aud"], ["https://wiki.free.law/"])

    def test_inactive_token_has_no_sub(self):
        self.assertEqual(self._introspect("nope"), {"active": False})


class DCRRefreshRefusalTest(TestCase):
    """With ``DCR_REFRESH_SWITCH`` on, the token endpoint answers
    ``invalid_grant`` to refreshes from applications registered through
    the retired DCR endpoint, so those clients start over with a fresh
    authorization. Applications registered by hand are unaffected, and
    so is everything while the switch is off.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.dcr_app = ApplicationFactory(
            client_type=Application.CLIENT_PUBLIC,
            registration_source=Application.RegistrationSource.DCR,
        )
        cls.manual_app = ApplicationFactory(
            client_type=Application.CLIENT_PUBLIC
        )

    def _refresh(self, application):
        """Mint a refresh token for *application* and spend it."""
        raw = f"refresh-{application.pk}"
        access = AccessToken(
            user=self.user,
            application=application,
            scope="api",
            expires=now() + timedelta(hours=1),
        )
        set_token_value(access, f"access-{application.pk}")
        access.save()
        refresh = RefreshToken(
            user=self.user, application=application, access_token=access
        )
        set_token_value(refresh, raw)
        refresh.save()
        return self.client.post(
            reverse("oauth2_provider:token"),
            {
                "grant_type": "refresh_token",
                "refresh_token": raw,
                "client_id": application.client_id,
            },
        )

    @override_switch(DCR_REFRESH_SWITCH, active=True)
    def test_dcr_app_refresh_is_refused(self):
        r = self._refresh(self.dcr_app)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(r.json()["error"], "invalid_grant")

    @override_switch(DCR_REFRESH_SWITCH, active=True)
    def test_manual_app_refresh_still_works(self):
        r = self._refresh(self.manual_app)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("access_token", r.json())

    @override_switch(DCR_REFRESH_SWITCH, active=False)
    def test_switch_off_leaves_dcr_apps_alone(self):
        r = self._refresh(self.dcr_app)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("access_token", r.json())

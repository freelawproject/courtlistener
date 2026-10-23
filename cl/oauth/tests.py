import base64
import hashlib
import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
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
    set_token_value,
)
from rest_framework.authtoken.models import Token

from cl.oauth.factories import ApplicationFactory
from cl.tests.cases import APITestCase, TestCase
from cl.tests.utils import parse_csp
from cl.users.factories import UserFactory, UserProfileWithParentsFactory

Application = get_application_model()
Grant = get_grant_model()
AccessToken = get_access_token_model()


@override_settings(RATELIMIT_ENABLE=False)
class DynamicClientRegistrationTest(APITestCase):
    """Tests for the RFC 7591 DCR endpoint at /o/register/.

    Rate limiting is disabled at the class level so that the many
    POSTs exercising validation branches don't trip the limiter.
    ``DynamicClientRegistrationRateLimitTest`` covers the limiter
    behavior itself.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse("oauth2_dcr")

    def test_confidential_client_registration(self):
        """A confidential client gets a client_id and client_secret."""
        resp = self.client.post(
            self.url,
            {
                "redirect_uris": ["https://mcp.example.com/callback"],
                "client_name": "Example MCP Client",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertIn("client_id", body)
        self.assertIn("client_secret", body)
        self.assertEqual(body["client_secret_expires_at"], 0)
        self.assertEqual(body["client_name"], "Example MCP Client")
        self.assertEqual(
            body["redirect_uris"], ["https://mcp.example.com/callback"]
        )
        self.assertEqual(body["grant_types"], ["authorization_code"])
        self.assertEqual(body["response_types"], ["code"])
        self.assertEqual(
            body["token_endpoint_auth_method"], "client_secret_basic"
        )
        # The app was persisted with the right type and provenance.
        app = Application.objects.get(client_id=body["client_id"])
        self.assertEqual(app.client_type, Application.CLIENT_CONFIDENTIAL)
        self.assertEqual(
            app.registration_source, Application.RegistrationSource.DCR
        )

    def test_public_client_registration_has_no_secret(self):
        """token_endpoint_auth_method=none yields a public client."""
        resp = self.client.post(
            self.url,
            {
                "redirect_uris": ["https://mcp.example.com/callback"],
                "token_endpoint_auth_method": "none",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertIn("client_id", body)
        self.assertNotIn("client_secret", body)
        self.assertNotIn("client_secret_expires_at", body)
        app = Application.objects.get(client_id=body["client_id"])
        self.assertEqual(app.client_type, Application.CLIENT_PUBLIC)

    def test_missing_redirect_uris_rejected(self):
        resp = self.client.post(self.url, {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_client_metadata")

    def test_empty_redirect_uris_rejected(self):
        resp = self.client.post(self.url, {"redirect_uris": []}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_http_loopback_allowed(self):
        for uri in (
            "http://localhost:8080/cb",
            "http://127.0.0.1:5555/cb",
            "http://[::1]:9000/cb",
        ):
            with self.subTest(uri=uri):
                resp = self.client.post(
                    self.url,
                    {"redirect_uris": [uri]},
                    format="json",
                )
                self.assertEqual(resp.status_code, 201, resp.content)

    def test_http_non_loopback_rejected(self):
        resp = self.client.post(
            self.url,
            {"redirect_uris": ["http://evil.example.com/cb"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("loopback", resp.json()["error_description"])

    def test_unsupported_scheme_rejected(self):
        resp = self.client.post(
            self.url,
            {"redirect_uris": ["javascript:alert(1)"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_disallowed_grant_type_rejected(self):
        resp = self.client.post(
            self.url,
            {
                "redirect_uris": ["https://mcp.example.com/cb"],
                "grant_types": ["client_credentials"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_authorization_code_grant_rejected(self):
        resp = self.client.post(
            self.url,
            {
                "redirect_uris": ["https://mcp.example.com/cb"],
                "grant_types": ["refresh_token"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_unsupported_token_auth_method_rejected(self):
        resp = self.client.post(
            self.url,
            {
                "redirect_uris": ["https://mcp.example.com/cb"],
                "token_endpoint_auth_method": "private_key_jwt",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_default_client_name_generated(self):
        resp = self.client.post(
            self.url,
            {"redirect_uris": ["https://mcp.example.com/cb"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["client_name"].startswith("MCP Client "))


@override_settings(
    OAUTH2_DCR_RATELIMIT="10/h",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            # Unique LOCATION so this cache is its own LocMemCache
            # instance, not shared with the default unnamed one.
            "LOCATION": "oauth-dcr-ratelimit-test",
        },
        # Preserve db_cache because some unrelated request paths
        # reference caches["db_cache"]. Not used by /o/register/.
        "db_cache": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
        },
    },
)
class DynamicClientRegistrationRateLimitTest(APITestCase):
    """The DCR endpoint is rate-limited per IP.

    Why the cache override: the project test runner defaults to
    ``--parallel=N`` (cl/tests/runner.py), and every parallel worker
    shares the same Redis. ``RestartRateLimitMixin.tearDownClass``
    runs ``DEL :1:rl:*`` which would wipe this test's counter mid-loop
    if a sibling worker tore down its class at the wrong moment. A
    process-local LocMemCache isolates us from sibling workers.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse("oauth2_dcr")
        cache.clear()

    def test_ratelimit_blocks_after_threshold(self):
        payload = {"redirect_uris": ["https://mcp.example.com/cb"]}
        for _ in range(10):
            resp = self.client.post(self.url, payload, format="json")
            self.assertEqual(resp.status_code, 201, resp.content)
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["error"], "rate_limited")


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
        self.assertIn("registration_endpoint", body)
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
        self.assertTrue(
            body["registration_endpoint"].startswith(body["issuer"])
        )
        # The registration endpoint must point at our DCR view.
        self.assertTrue(body["registration_endpoint"].endswith("/o/register/"))

    def test_scopes_supported_excludes_oidc_scopes_when_oidc_disabled(self):
        with patch.dict(settings.OAUTH2_PROVIDER, {"OIDC_ENABLED": False}):
            resp = self.client.get(self.url)
        self.assertEqual(resp.json()["scopes_supported"], ["api"])

    def test_scopes_supported_lists_only_dcr_scopes_when_oidc_enabled(self):
        with patch.dict(settings.OAUTH2_PROVIDER, {"OIDC_ENABLED": True}):
            resp = self.client.get(self.url)
        self.assertEqual(resp.json()["scopes_supported"], ["api", "openid"])


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


@override_settings(
    OAUTH2_PROVIDER={**settings.OAUTH2_PROVIDER, "OIDC_ENABLED": True}
)
class DCRScopeRestrictionTest(TestCase):
    """Dynamically registered apps may request only ``api`` and ``openid``.

    Anyone can register an app through DCR under any name, so the identity
    and wiki scopes are reserved for applications we create by hand.
    """

    REDIRECT_URI = "https://client.example.com/callback"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.dcr_app = ApplicationFactory(
            client_type=Application.CLIENT_PUBLIC,
            redirect_uris=cls.REDIRECT_URI,
            registration_source=Application.RegistrationSource.DCR,
        )
        cls.manual_app = ApplicationFactory(
            client_type=Application.CLIENT_PUBLIC,
            redirect_uris=cls.REDIRECT_URI,
        )

    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.user)

    def _authorize(self, application, scope: str):
        """GET the consent screen for *application* requesting *scope*."""
        return self.client.get(
            reverse("oauth2_provider:authorize"),
            {
                "response_type": "code",
                "client_id": application.client_id,
                "redirect_uri": self.REDIRECT_URI,
                "scope": scope,
                "state": "xyz",
                "code_challenge": s256_challenge("a" * 64),
                "code_challenge_method": "S256",
            },
        )

    def test_dcr_app_may_request_api_and_openid(self):
        r = self._authorize(self.dcr_app, "api openid")
        self.assertEqual(r.status_code, 200, r.content)

    def test_dcr_app_is_refused_other_scopes(self):
        for scope in ("api wiki", "openid email", "openid profile", "wiki"):
            with self.subTest(scope=scope):
                r = self._authorize(self.dcr_app, scope)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r["Location"].startswith(self.REDIRECT_URI))
                self.assertIn("error=invalid_scope", r["Location"])

    def test_manual_app_may_request_every_scope(self):
        r = self._authorize(self.manual_app, "openid api wiki email profile")
        self.assertEqual(r.status_code, 200, r.content)


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


class OAuthPopupCoopTest(TestCase):
    """The pages an OAuth popup can render opt out of opener isolation.

    Popup-based OAuth clients (Microsoft Copilot among them) learn the
    outcome of authorization through the popup's ``window.opener``, which
    the site-wide COOP ``same-origin`` header severs permanently on the
    first CourtListener page shown (issue #7633). The ``unsafe-none``
    opt-out must cover exactly the authorization journey and nothing else.
    """

    REDIRECT_URI = "https://mcp.example.com/callback"
    COOP = "Cross-Origin-Opener-Policy"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.application = ApplicationFactory(
            client_type=Application.CLIENT_PUBLIC,
            redirect_uris=cls.REDIRECT_URI,
        )

    def _authorize_params(self) -> dict[str, str]:
        """Valid S256 authorize parameters for the test application."""
        return {
            "response_type": "code",
            "client_id": self.application.client_id,
            "redirect_uri": self.REDIRECT_URI,
            "scope": "api",
            "state": "xyz",
            "code_challenge": s256_challenge("a" * 64),
            "code_challenge_method": "S256",
        }

    def test_popup_journey_pages_opt_out(self) -> None:
        """Sign-in and every page it links to serve COOP unsafe-none."""
        journey = (
            ("sign-in", {}),
            ("register", {}),
            ("register_success", {"next": "/"}),
            ("password_reset", {}),
            ("password_reset_done", {}),
        )
        for view_name, params in journey:
            with self.subTest(view=view_name):
                response = self.client.get(reverse(view_name), params)
                self.assertEqual(
                    response.headers.get(self.COOP), "unsafe-none"
                )

    def test_consent_page_opts_out(self) -> None:
        """The consent screen itself serves COOP unsafe-none."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("oauth2_provider:authorize"), self._authorize_params()
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.headers.get(self.COOP), "unsafe-none")

    def test_authorize_redirects_opt_out(self) -> None:
        """Redirects from the authorize view carry the opt-out too, since
        browsers evaluate COOP on redirect responses as well."""
        response = self.client.get(
            reverse("oauth2_provider:authorize"), self._authorize_params()
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get(self.COOP), "unsafe-none")

    def test_rest_of_site_keeps_isolation(self) -> None:
        """Pages outside the popup journey keep the hardened default."""
        response = self.client.get(reverse("view_settings"))
        self.assertEqual(response.headers.get(self.COOP), "same-origin")

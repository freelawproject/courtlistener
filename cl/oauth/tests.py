import base64
import hashlib
from datetime import timedelta
from unittest.mock import patch

import time_machine
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from oauth2_provider.models import (
    get_access_token_model,
    get_application_model,
    get_grant_model,
    get_id_token_model,
    get_refresh_token_model,
)

from cl.oauth.cleanup_utils import (
    delete_unconfirmed_applications,
    run_cleanup_pass,
    unconfirmed_applications,
)
from cl.oauth.factories import ApplicationFactory
from cl.tests.cases import APITestCase, SimpleTestCase, TestCase
from cl.tests.utils import parse_csp
from cl.users.factories import UserFactory

Application = get_application_model()
Grant = get_grant_model()
AccessToken = get_access_token_model()
RefreshToken = get_refresh_token_model()
IDToken = get_id_token_model()


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
        # The app was persisted with the right type.
        app = Application.objects.get(client_id=body["client_id"])
        self.assertEqual(app.client_type, Application.CLIENT_CONFIDENTIAL)

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

    def test_scopes_supported_excludes_openid_when_oidc_disabled(self):
        with patch.dict(settings.OAUTH2_PROVIDER, {"OIDC_ENABLED": False}):
            resp = self.client.get(self.url)
        self.assertEqual(resp.json()["scopes_supported"], ["api"])

    def test_scopes_supported_includes_openid_when_oidc_enabled(self):
        with patch.dict(settings.OAUTH2_PROVIDER, {"OIDC_ENABLED": True}):
            resp = self.client.get(self.url)
        scopes = resp.json()["scopes_supported"]
        self.assertIn("api", scopes)
        self.assertIn("openid", scopes)


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


class PKCEMethodEnforcementTest(SimpleTestCase):
    """The RFC 8414 metadata advertises S256-only PKCE, but oauthlib
    3.3.1 defaults an absent ``code_challenge_method`` to ``"plain"`` and
    django-oauth-toolkit 3.2 has no setting to restrict which method is
    accepted. ``cl.oauth.apps.OAuthConfig.ready`` narrows oauthlib's
    method dict to S256 only; these tests confirm the patch took effect.
    """

    def _grant(self):
        from oauthlib.oauth2.rfc6749.grant_types.authorization_code import (
            AuthorizationCodeGrant,
        )

        return AuthorizationCodeGrant(request_validator=None)

    def test_only_s256_registered(self):
        from oauthlib.oauth2.rfc6749.grant_types.authorization_code import (
            AuthorizationCodeGrant,
        )

        self.assertEqual(
            set(AuthorizationCodeGrant._code_challenge_methods),
            {"S256"},
        )

    def test_plain_verification_rejected(self):
        # With plain removed, oauthlib refuses to run the weak transform.
        # In the actual HTTP flow this manifests as an
        # UnsupportedCodeChallengeMethodError earlier in
        # validate_authorization_request; here we drive the leaf
        # function directly to prove the method isn't registered.
        with self.assertRaises(NotImplementedError):
            self._grant().validate_code_challenge("abc", "plain", "abc")

    def test_s256_verification_still_works(self):
        import base64
        import hashlib

        verifier = "abc"
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            )
            .decode()
            .rstrip("=")
        )
        self.assertTrue(
            self._grant().validate_code_challenge(challenge, "S256", verifier)
        )


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


class UnconfirmedApplicationCleanupTest(TestCase):
    """The application cleanup deletes never-authorized DCR apps only."""

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        expires = now() + timedelta(hours=1)
        redirect_uri = "https://client.example.com/callback"
        with time_machine.travel(now() - timedelta(days=2), tick=False):
            cls.stale = ApplicationFactory(name="stale, never authorized")
            cls.owned = ApplicationFactory(name="owned", user=cls.user)
            cls.in_house = ApplicationFactory(
                name="in-house", skip_authorization=True
            )
            cls.with_grant = ApplicationFactory(name="consent pending")
            cls.with_access_token = ApplicationFactory(name="access token")
            cls.with_refresh_token = ApplicationFactory(name="refresh token")
            cls.with_id_token = ApplicationFactory(name="id token")
        cls.fresh = ApplicationFactory(name="registered just now")
        Grant.objects.create(
            user=cls.user,
            code="grant-code",
            application=cls.with_grant,
            expires=expires,
            redirect_uri=redirect_uri,
        )
        AccessToken.objects.create(
            user=cls.user,
            token="access-token",
            application=cls.with_access_token,
            expires=expires,
        )
        RefreshToken.objects.create(
            user=cls.user,
            token="refresh-token",
            application=cls.with_refresh_token,
        )
        IDToken.objects.create(
            user=cls.user, application=cls.with_id_token, expires=expires
        )
        cls.kept = [
            cls.owned,
            cls.in_house,
            cls.with_grant,
            cls.with_access_token,
            cls.with_refresh_token,
            cls.with_id_token,
            cls.fresh,
        ]

    def assertKeptApplicationsExist(self):
        for app in self.kept:
            with self.subTest(app=app.name):
                self.assertTrue(Application.objects.filter(pk=app.pk).exists())

    def test_only_stale_unauthorized_apps_are_candidates(self):
        candidates = unconfirmed_applications(min_age=timedelta(days=1))
        self.assertEqual(
            list(candidates.values_list("pk", flat=True)), [self.stale.pk]
        )

    def test_max_age_excludes_older_registrations(self):
        old_enough = unconfirmed_applications(
            min_age=timedelta(days=1), max_age=timedelta(days=3)
        )
        self.assertEqual(old_enough.count(), 1)
        too_old = unconfirmed_applications(
            min_age=timedelta(days=1), max_age=timedelta(hours=36)
        )
        self.assertEqual(too_old.count(), 0)

    def test_delete_removes_candidates_and_keeps_the_rest(self):
        deleted = delete_unconfirmed_applications(
            min_age=timedelta(days=1), batch_size=100, pause_seconds=0
        )
        self.assertEqual(deleted, 1)
        self.assertFalse(Application.objects.filter(pk=self.stale.pk).exists())
        self.assertKeptApplicationsExist()

    def test_dry_run_counts_without_deleting(self):
        deleted = delete_unconfirmed_applications(
            min_age=timedelta(days=1),
            batch_size=100,
            pause_seconds=0,
            dry_run=True,
        )
        self.assertEqual(deleted, 1)
        self.assertTrue(Application.objects.filter(pk=self.stale.pk).exists())

    def test_batches_until_no_candidates_remain(self):
        with time_machine.travel(now() - timedelta(days=2), tick=False):
            ApplicationFactory.create_batch(4)
        deleted = delete_unconfirmed_applications(
            min_age=timedelta(days=1), batch_size=2, pause_seconds=0
        )
        self.assertEqual(deleted, 5)
        self.assertEqual(
            unconfirmed_applications(min_age=timedelta(days=1)).count(), 0
        )
        self.assertKeptApplicationsExist()

    @patch("cl.oauth.cleanup_utils.clear_expired")
    def test_pass_does_not_clear_tokens_yet(self, mock_clear_expired):
        """Token clearing is staged behind the application backlog."""
        run_cleanup_pass()
        mock_clear_expired.assert_not_called()
        self.assertFalse(Application.objects.filter(pk=self.stale.pk).exists())
        self.assertKeptApplicationsExist()


class CleanOAuthTablesDaemonTest(TestCase):
    """The daemon command runs passes and honors its flags."""

    @classmethod
    def setUpTestData(cls):
        with time_machine.travel(now() - timedelta(days=2), tick=False):
            cls.stale = ApplicationFactory(name="stale, never authorized")

    def test_one_pass_deletes_unconfirmed_applications(self):
        call_command("clean_oauth_tables_daemon", "--testing-iterations=1")
        self.assertFalse(Application.objects.filter(pk=self.stale.pk).exists())

    def test_dry_run_deletes_nothing(self):
        call_command(
            "clean_oauth_tables_daemon", "--testing-iterations=1", "--dry-run"
        )
        self.assertTrue(Application.objects.filter(pk=self.stale.pk).exists())

    @override_settings(OAUTH_CLEANUP_DAEMON_ENABLED=False)
    def test_disabled_daemon_exits_without_deleting(self):
        call_command("clean_oauth_tables_daemon", "--testing-iterations=1")
        self.assertTrue(Application.objects.filter(pk=self.stale.pk).exists())

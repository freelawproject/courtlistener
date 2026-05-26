from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from oauth2_provider.models import get_application_model

from cl.tests.cases import APITestCase, SimpleTestCase

Application = get_application_model()


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

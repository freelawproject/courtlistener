from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings
from waffle.testutils import override_flag

from cl.api.middleware import ReplicaRoutingMiddleware
from cl.api.routers import (
    ReplicaRouter,
    _use_replica,
    reset_replica_routing,
    set_replica_routing,
)
from cl.tests.cases import SimpleTestCase, TestCase

DATABASES_WITH_REPLICA = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "courtlistener",
    },
    "replica": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "courtlistener_replica",
    },
}

DATABASES_WITHOUT_REPLICA = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "courtlistener",
    },
}


class ReplicaRouterTest(SimpleTestCase):
    """Tests for the ReplicaRouter Django database router."""

    def setUp(self):
        self.router = ReplicaRouter()

    def test_db_for_read_returns_replica_when_context_set(self):
        """Reads go to replica when the ContextVar is set."""
        token = set_replica_routing(True)
        try:
            result = self.router.db_for_read(None)
            self.assertIsNotNone(result)
        finally:
            reset_replica_routing(token)

    def test_db_for_read_returns_none_when_context_not_set(self):
        """Reads fall through to default when ContextVar is not set."""
        result = self.router.db_for_read(None)
        self.assertIsNone(result)

    def test_db_for_write_always_returns_none(self):
        """Writes always fall through to default, even when routing is on."""
        token = set_replica_routing(True)
        try:
            result = self.router.db_for_write(None)
            self.assertIsNone(result)
        finally:
            reset_replica_routing(token)

    def test_allow_relation_returns_true(self):
        """Relations between databases are always allowed."""
        self.assertTrue(self.router.allow_relation(None, None))

    def test_allow_migrate_returns_none(self):
        """Router does not interfere with migrations."""
        self.assertIsNone(self.router.allow_migrate("default", "search"))

    def test_context_var_resets_correctly(self):
        """ContextVar resets to False after token reset."""
        token = set_replica_routing(True)
        self.assertTrue(_use_replica.get())
        reset_replica_routing(token)
        self.assertFalse(_use_replica.get())


@override_settings(
    DATABASES=DATABASES_WITH_REPLICA,
    WAFFLE_CACHE_PREFIX="test_replica_routing",
    API_READ_DATABASES=["replica"],
)
@override_flag("replica-reads", active=True)
class ReplicaRoutingMiddlewareTest(TestCase):
    """Tests for the replica_routing_middleware."""

    def setUp(self):
        self.factory = RequestFactory()

    def _get_middleware(self, response_fn=None):
        """Create middleware with a get_response that captures the
        ContextVar value during the request."""
        captured = {}

        def get_response(request: HttpRequest) -> HttpResponse:
            captured["use_replica"] = _use_replica.get(False)
            if response_fn:
                return response_fn(request)
            return HttpResponse("OK")

        middleware = ReplicaRoutingMiddleware(get_response)
        return middleware, captured

    def test_api_get_enables_replica_routing(self):
        """GET /api/rest/v4/... with flag active sets ContextVar."""
        middleware, captured = self._get_middleware()
        request = self.factory.get("/api/rest/v4/dockets/")
        middleware(request)
        self.assertTrue(captured["use_replica"])

    def test_api_head_enables_replica_routing(self):
        """HEAD requests to API also route to replica."""
        middleware, captured = self._get_middleware()
        request = self.factory.head("/api/rest/v4/dockets/")
        middleware(request)
        self.assertTrue(captured["use_replica"])

    def test_api_post_does_not_enable_replica_routing(self):
        """POST requests never route to replica."""
        middleware, captured = self._get_middleware()
        request = self.factory.post("/api/rest/v4/dockets/")
        middleware(request)
        self.assertFalse(captured["use_replica"])

    def test_api_put_does_not_enable_replica_routing(self):
        """PUT requests never route to replica."""
        middleware, captured = self._get_middleware()
        request = self.factory.put("/api/rest/v4/dockets/")
        middleware(request)
        self.assertFalse(captured["use_replica"])

    def test_frontend_get_does_not_enable_replica_routing(self):
        """GET requests to non-API paths stay on default."""
        middleware, captured = self._get_middleware()
        request = self.factory.get("/some-page/")
        middleware(request)
        self.assertFalse(captured["use_replica"])

    @override_settings(
        WAFFLE_CACHE_PREFIX="test_replica_routing_flag_inactive"
    )
    @override_flag("replica-reads", active=False)
    def test_flag_inactive_does_not_enable_replica_routing(self):
        """When the waffle flag is inactive, no routing happens."""
        middleware, captured = self._get_middleware()
        request = self.factory.get("/api/rest/v4/dockets/")
        middleware(request)
        self.assertFalse(captured["use_replica"])

    @override_settings(DATABASES=DATABASES_WITHOUT_REPLICA)
    def test_no_replica_db_configured(self):
        """When no replica DB is configured, routing is skipped."""
        middleware, captured = self._get_middleware()
        request = self.factory.get("/api/rest/v4/dockets/")
        middleware(request)
        self.assertFalse(captured["use_replica"])

    def test_context_var_resets_after_request(self):
        """ContextVar resets to False after the request completes."""
        middleware, _ = self._get_middleware()
        request = self.factory.get("/api/rest/v4/dockets/")
        middleware(request)
        self.assertFalse(_use_replica.get(False))

    def test_context_var_resets_on_exception(self):
        """ContextVar resets even when the view raises an exception."""

        def error_view(request):
            raise ValueError("Test exception")

        middleware, _ = self._get_middleware(response_fn=error_view)
        request = self.factory.get("/api/rest/v4/dockets/")
        with self.assertRaises(ValueError):
            middleware(request)
        self.assertFalse(_use_replica.get(False))

    def test_v3_api_also_routes_to_replica(self):
        """v3 API requests are also routed to replica."""
        middleware, captured = self._get_middleware()
        request = self.factory.get("/api/rest/v3/dockets/")
        middleware(request)
        self.assertTrue(captured["use_replica"])

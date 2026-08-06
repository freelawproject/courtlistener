import importlib.machinery
import sys
import types
from pathlib import Path

import django
from django.conf import settings

from cl.tests.cases import TestCase

# Minimal Django configuration
if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "rest_framework",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        SECRET_KEY="test",
    )
    django.setup()

from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

# Stub out heavy modules imported by cl.api.pagination
cl_path = Path(__file__).resolve().parents[1]
sys.modules.setdefault("cl", types.ModuleType("cl"))
sys.modules["cl"].__path__ = [str(cl_path)]
sys.modules.setdefault("cl.api", types.ModuleType("cl.api"))
sys.modules["cl.api"].__path__ = [str(cl_path / "api")]

celery_stub = types.ModuleType("cl.celery_init")
celery_stub.app = object()
sys.modules.setdefault("cl.celery_init", celery_stub)

api_utils_stub = types.ModuleType("cl.search.api_utils")
api_utils_stub.CursorESList = object()
sys.modules.setdefault("cl.search.api_utils", api_utils_stub)
models_stub = types.ModuleType("cl.search.models")
models_stub.SEARCH_TYPES = {}
sys.modules.setdefault("cl.search.models", models_stub)
types_stub = types.ModuleType("cl.search.types")
types_stub.ESCursor = type("ESCursor", (), {})
sys.modules.setdefault("cl.search.types", types_stub)

spec = Path(cl_path / "api" / "pagination.py")
module_name = "cl.api.pagination"
loader = importlib.machinery.SourceFileLoader(module_name, str(spec))
pagination = types.ModuleType(module_name)
loader.exec_module(pagination)
LargePagePagination = pagination.LargePagePagination


class LargePagePaginationTest(TestCase):
    def setUp(self):
        self.paginator = LargePagePagination()

    def _get_page_size(self, params=None):
        factory = APIRequestFactory()
        request = Request(factory.get("/", params or {}))
        request.version = "v4"
        return self.paginator.get_page_size(request)

    def test_default_page_size(self):
        self.assertEqual(self._get_page_size(), 20)

    def test_small_page_with_plain_text(self):
        self.assertEqual(self._get_page_size({"page_size": 10}), 10)

    def test_large_page_plain_text_included(self):
        self.assertEqual(
            self._get_page_size(
                {"page_size": 100, "include_plain_text": "true"}
            ),
            20,
        )

    def test_large_page_plain_text_excluded(self):
        self.assertEqual(
            self._get_page_size(
                {"page_size": 100, "include_plain_text": "false"}
            ),
            100,
        )

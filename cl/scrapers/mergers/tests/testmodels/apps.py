"""Django app config for the merger framework's test-only models.

This app is only added to ``INSTALLED_APPS`` during testing. Its models
target the ``mergers_test`` database (an in-memory SQLite instance) via
the ``MergersTestRouter`` so the framework can exercise real Django ORM
behavior without pulling in PG-specific dependencies (``pghistory``,
``pgtrigger``, etc.) from production models.
"""

from django.apps import AppConfig


class TestModelsConfig(AppConfig):
    name = "cl.scrapers.mergers.tests.testmodels"
    label = "mergers_testmodels"
    default_auto_field = "django.db.models.BigAutoField"

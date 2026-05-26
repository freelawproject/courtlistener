"""Database router for the merger test-only models.

All queries on the ``mergers_testmodels`` app are routed to the
``mergers_test`` database (an in-memory SQLite instance). Conversely,
only ``mergers_testmodels`` migrations run on that database — no other
app's tables get created there.
"""

from typing import Any


class MergersTestRouter:
    APP_LABEL = "mergers_testmodels"
    DB_ALIAS = "mergers_test"

    def db_for_read(
        self, model: type, **hints: Any
    ) -> str | None:
        if model._meta.app_label == self.APP_LABEL:
            return self.DB_ALIAS
        return None

    def db_for_write(
        self, model: type, **hints: Any
    ) -> str | None:
        if model._meta.app_label == self.APP_LABEL:
            return self.DB_ALIAS
        return None

    def allow_relation(
        self, obj1: Any, obj2: Any, **hints: Any
    ) -> bool | None:
        # Allow relations within mergers_testmodels.
        if (
            obj1._meta.app_label == self.APP_LABEL
            and obj2._meta.app_label == self.APP_LABEL
        ):
            return True
        # Otherwise defer to other routers.
        return None

    def allow_migrate(
        self,
        db: str,
        app_label: str,
        model_name: str | None = None,
        **hints: Any,
    ) -> bool | None:
        if app_label == self.APP_LABEL:
            return db == self.DB_ALIAS
        if db == self.DB_ALIAS:
            # The mergers_test DB only holds mergers_testmodels tables.
            return False
        return None

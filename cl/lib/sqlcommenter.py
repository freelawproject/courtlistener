from contextlib import ExitStack
from typing import Any

from django.db import connections


def add_sql_comment(sql: str, **meta: Any) -> str:
    """
    Append a SQL comment containing key=value pairs from meta.
    """
    if not meta:
        return sql

    comment_parts = [
        f"{key}={value}" for key, value in meta.items() if value is not None
    ]
    if not comment_parts:
        return sql

    comment = "/* " + ", ".join(comment_parts) + " */"
    sql = sql.rstrip()

    if sql.endswith(";"):
        return sql[:-1] + " " + comment + ";"
    return sql + " " + comment


class SqlCommenter:
    """
    Middleware to append a comment to each database query with details about
    the framework and the execution context.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with ExitStack() as stack:
            for db_alias in connections:
                stack.enter_context(
                    connections[db_alias].execute_wrapper(
                        QueryWrapper(request)
                    )
                )
            return self.get_response(request)


class QueryWrapper:
    def __init__(self, request):
        self.request = request

    def get_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Extract relevant context information from the request for SQL comments.

        This helper mirrors the behavior and intent of the `get_context` method in
        `pghistory.middleware.HistoryMiddleware`, providing similar request-scoped
        metadata (such as the current user and request path) for use in query
        annotation.
        """
        user = (
            self.request.user._meta.pk.get_db_prep_value(
                self.request.user.pk, context["connection"]
            )
            if hasattr(self.request, "user")
            and hasattr(self.request.user, "_meta")
            else None
        )
        return {"user_id": user, "url": self.request.path}

    def __call__(self, execute, sql, params, many, context):
        context_info = self.get_context(context)
        sql_with_comment = add_sql_comment(sql, **context_info)
        return execute(sql_with_comment, params, many, context)

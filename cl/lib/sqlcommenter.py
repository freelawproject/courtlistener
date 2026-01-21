from contextlib import ExitStack
from typing import Any
from urllib.parse import quote

from django.conf import settings
from django.db import connections
from django.utils.functional import SimpleLazyObject, empty


def escape_sql_comment_value(value: Any) -> str | None:
    """Safely escape a value for inclusion in SQL comments."""
    if value is None:
        return None

    # Coerce to string early
    s = str(value)

    # Normalize and remove newlines
    s = s.replace("\r", " ").replace("\n", " ")

    # URL-encode to escape special characters
    quoted = quote(s)

    # Double % signs for SQL compatibility
    return quoted.replace("%", "%%")


def add_sql_comment(sql: str, **meta: Any) -> str:
    """
    Append a SQL comment containing key=value pairs from meta.
    """
    if not meta:
        return sql

    comment_parts = []
    for key, value in meta.items():
        if not value:
            continue
        escaped_value = escape_sql_comment_value(value)
        comment_parts.append(f"{key}='{escaped_value}'")

    if not comment_parts:
        return sql

    comment = "/* " + ", ".join(comment_parts) + " */"
    sql = sql.rstrip()

    if sql.endswith(";"):
        return comment + " " + sql[:-1] + ";"
    return comment + " " + sql


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

    def get_context(self) -> dict[str, Any]:
        """
        Extract relevant context information from the request for SQL comments.
        """
        user = None
        if hasattr(self.request, "user"):
            user_obj = self.request.user
            # Check if SimpleLazyObject has been evaluated to avoid recursion.
            # Accessing is_authenticated on an unevaluated lazy user triggers a
            # database query, which would go through this wrapper again,
            # creating infinite recursion. See #6773.
            if isinstance(user_obj, SimpleLazyObject):
                # Access _wrapped to check if lazy object has been evaluated.
                # Once evaluated, it proxies to the User model.
                if (
                    user_obj._wrapped is not empty  # type: ignore[attr-defined]
                    and user_obj.is_authenticated  # type: ignore[attr-defined]
                ):
                    user = user_obj.pk  # type: ignore[attr-defined]
            elif user_obj.is_authenticated:
                user = user_obj.pk

        path = None
        resolver_match = self.request.resolver_match
        if resolver_match:
            path = self.request.path
            if path and len(path) > settings.SQLCOMMENTER_MAX_PATH_LENGTH:
                path = f"{path[: settings.SQLCOMMENTER_MAX_PATH_LENGTH]}…"

        return {
            "user_id": user,
            "url": path,
            "url-name": resolver_match.view_name if resolver_match else None,
        }

    def __call__(self, execute, sql, params, many, context):
        sql_with_comment = add_sql_comment(sql, **self.get_context())
        return execute(sql_with_comment, params, many, context)

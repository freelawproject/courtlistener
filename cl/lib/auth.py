from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.db.models import QuerySet, Value
from django.db.models.functions import Lower


def filter_by_email(queryset: QuerySet[User], email: str) -> QuerySet[User]:
    """Narrow a queryset of users to those holding an email address.

    The one place that decides when two addresses are the same address. Sign
    in, registration, email confirmation and password reset all have to agree
    on that, so they all come through here.

    Prefer this to ``email__iexact``, which compiles to ``UPPER()`` and so
    can't use the auth_user_email_lower_idx index, and which folds case in
    Python on one side — ``str.lower()`` and Postgres's ``LOWER()`` disagree
    on some non-ASCII characters.

    Callers keep their own idea of *which* accounts they want: registration
    wants stubs, confirmation wants everybody, sign-in wants neither. This
    only settles the address.

    :param queryset: The users to narrow.
    :param email: The address to match. An empty one matches nothing, rather
    than matching every account with a blank address, which is a legal value
    on auth_user.
    :return: The narrowed queryset.
    """
    if not email:
        return queryset.none()
    return queryset.alias(email_lower=Lower("email")).filter(
        email_lower=Lower(Value(email))
    )


def group_required(*group_names):
    """Verify user group membership

    :param group_names: Array of strings
    :return: Whether the user is in one of the groups
    """

    def in_groups(u):
        if u.is_authenticated:
            if bool(u.groups.filter(name__in=group_names)) | u.is_superuser:
                return True
        return False

    return user_passes_test(in_groups)

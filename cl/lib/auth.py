from django.contrib.auth.decorators import user_passes_test


def group_required(*group_names):
    """Verify user group memebership

    :param group_names: Array of strings
    :return: Whether the user is in one of the groups
    """

    def in_groups(u):
        if u.is_authenticated:
            if bool(u.groups.filter(name__in=group_names)) | u.is_superuser:
                return True
        return False

    return user_passes_test(in_groups)

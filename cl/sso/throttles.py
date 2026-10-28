from django.contrib.auth.models import User

from cl.api.utils import apply_membership_throttles, clear_membership_throttles
from cl.lib.decorators import clear_tiered_cache
from cl.sso.membership import get_effective_membership
from cl.sso.models import Organization


def sync_user_throttles(user: User, clear_cache: bool = True) -> None:
    """Make a person's membership API rates match their effective membership.

    Neon webhooks keep rates in step with individual memberships; this does
    the same when an organization membership is created, removed or changes
    level. Manually set throttles are never touched.

    :param user: Whose rates to sync.
    :param clear_cache: Clear the throttle cache afterwards. Batch callers
    pass False and clear it once at the end.
    """
    membership = get_effective_membership(user)
    if membership is None:
        clear_membership_throttles(user)
        return
    apply_membership_throttles(user, membership.level, clear_cache=clear_cache)


def sync_organization_throttles(organization: Organization) -> None:
    """Sync API rates for every member of an organization.

    :param organization: The organization whose members to update.
    """
    for membership in organization.memberships.select_related("user"):
        sync_user_throttles(membership.user, clear_cache=False)
    clear_tiered_cache()

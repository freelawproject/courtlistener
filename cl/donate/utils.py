from cl.alerts.constants import (
    LEGACY_MEMBERSHIP_HELP_URL,
    MEMBERSHIP_UPGRADE_BASE_URL,
)
from cl.donate.models import NeonMembership, NeonMembershipLevel

# Where members sign in to Neon to change their plan, payment frequency,
# profile or contact information.
DONOR_PORTAL_URL = "https://donate.free.law/login"


def get_membership_upgrade_url(membership: NeonMembership) -> str:
    """Get the best place for a member to go to get more from their plan.

    Legacy memberships can't be upgraded through Neon's upgrade flow (it 404s,
    see #7136), so they are sent to a help page that explains the alternatives.
    A membership without a Neon ID can't be used to build the upgrade URL, so
    those members are sent to the donor portal instead.

    :param membership: The member's membership.
    :return: A URL the member can follow to upgrade or manage their plan.
    """
    if membership.level == NeonMembershipLevel.LEGACY:
        return LEGACY_MEMBERSHIP_HELP_URL
    if not membership.neon_id:
        return DONOR_PORTAL_URL
    return f"{MEMBERSHIP_UPGRADE_BASE_URL}{membership.neon_id}"

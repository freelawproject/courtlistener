from dataclasses import dataclass

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist

from cl.donate.models import NeonMembershipLevel
from cl.sso.models import Organization, OrganizationMembership


@dataclass(frozen=True)
class EffectiveMembership:
    """The membership whose benefits a person gets right now.

    ``organization`` is None when the benefits come from the person's own
    Neon membership. ``neon_id`` is the Neon membership ID that upgrade links
    point at; it is empty for organization memberships, which people can't
    upgrade themselves.
    """

    level: int
    neon_id: str
    organization: Organization | None = None

    @property
    def is_organization(self) -> bool:
        """Whether the benefits come from an organization."""
        return self.organization is not None

    @property
    def level_display(self) -> str:
        """The membership level's name, as shown to members."""
        return dict(NeonMembershipLevel.TYPES).get(self.level, "")


def get_effective_membership(
    user: AbstractBaseUser | AnonymousUser,
) -> EffectiveMembership | None:
    """Work out which membership, if any, gives a person their benefits.

    Use this instead of reading ``user.membership`` directly whenever the
    question is "what benefits does this person get?". Order:

    1. The person's own active ``NeonMembership``. It wins over any
       organization membership, so a paying member keeps the upgrade links
       and quotas they bought.
    2. Otherwise, an active organization in which they hold a seat. If
       there are several (rare), the one they joined first, so the answer
       doesn't change from one request to the next.

    For people without an active Neon membership this costs one query per
    call, so callers checking several things should call it once.

    :param user: Who to check.
    :return: The membership in effect, or None for free users.
    """
    if not user.is_authenticated:
        return None
    try:
        own = user.membership  # type: ignore[union-attr]
    except ObjectDoesNotExist:
        own = None
    if own is not None and own.is_active:
        return EffectiveMembership(level=own.level, neon_id=own.neon_id)

    org_membership = (
        OrganizationMembership.objects.filter(
            user=user,
            has_seat=True,
            organization__in=Organization.objects.active(),
        )
        .select_related("organization")
        .order_by("date_created")
        .first()
    )
    if org_membership is None:
        return None
    organization = org_membership.organization
    return EffectiveMembership(
        level=organization.membership_level,  # type: ignore[arg-type]
        neon_id="",
        organization=organization,
    )

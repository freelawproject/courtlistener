"""Constants for the API app.

Currently scoped to membership-throttle rate tables. Keeping these
out of utils.py makes them trivially importable from management
commands / scripts / tests without dragging in the rest of the
throttle machinery.
"""

from cl.donate.models import NeonMembershipLevel

# Rate sets per tier. The "size" dimension on group memberships
# (Smallest/Small/Medium/Large/Unlimited) affects seat count, not
# per-user throughput, so all sizes within a tier share the same
# per-user rates. HeyCounsel tiers mirror the matching individual
# tier.
TIER_1_RATES = ["10/min", "75/hour", "300/day"]
TIER_2_RATES = ["15/min", "150/hour", "600/day"]
TIER_3_RATES = ["20/min", "250/hour", "1000/day"]
TIER_4_RATES = ["25/min", "300/hour", "1400/day"]
EDU_RATES = ["20/min", "1000/hour"]

# Membership levels not present in this dict result in a no-op when
# the helper runs — by design for Commercial (manual setup) and
# unused legacy levels (BASIC, GROUP_SMALLEST..UNLIMITED).
LEVEL_TO_RATES: dict[int, list[str]] = {
    # Individual memberships
    NeonMembershipLevel.LEGACY: TIER_1_RATES,
    NeonMembershipLevel.TIER_1: TIER_1_RATES,
    NeonMembershipLevel.TIER_2: TIER_2_RATES,
    NeonMembershipLevel.TIER_3: TIER_3_RATES,
    NeonMembershipLevel.TIER_4: TIER_4_RATES,
    NeonMembershipLevel.LSO_1: TIER_1_RATES,
    NeonMembershipLevel.EDU: EDU_RATES,
    # Group Tier 1
    NeonMembershipLevel.GROUP_T1_SMALLEST: TIER_1_RATES,
    NeonMembershipLevel.GROUP_T1_SMALL: TIER_1_RATES,
    NeonMembershipLevel.GROUP_T1_MEDIUM: TIER_1_RATES,
    NeonMembershipLevel.GROUP_T1_LARGE: TIER_1_RATES,
    NeonMembershipLevel.GROUP_T1_UNLIMITED: TIER_1_RATES,
    # Group Tier 2
    NeonMembershipLevel.GROUP_T2_SMALLEST: TIER_2_RATES,
    NeonMembershipLevel.GROUP_T2_SMALL: TIER_2_RATES,
    NeonMembershipLevel.GROUP_T2_MEDIUM: TIER_2_RATES,
    NeonMembershipLevel.GROUP_T2_LARGE: TIER_2_RATES,
    NeonMembershipLevel.GROUP_T2_UNLIMITED: TIER_2_RATES,
    # Group Tier 3
    NeonMembershipLevel.GROUP_T3_SMALLEST: TIER_3_RATES,
    NeonMembershipLevel.GROUP_T3_SMALL: TIER_3_RATES,
    NeonMembershipLevel.GROUP_T3_MEDIUM: TIER_3_RATES,
    NeonMembershipLevel.GROUP_T3_LARGE: TIER_3_RATES,
    NeonMembershipLevel.GROUP_T3_UNLIMITED: TIER_3_RATES,
    # Group Tier 4
    NeonMembershipLevel.GROUP_T4_SMALLEST: TIER_4_RATES,
    NeonMembershipLevel.GROUP_T4_SMALL: TIER_4_RATES,
    NeonMembershipLevel.GROUP_T4_MEDIUM: TIER_4_RATES,
    NeonMembershipLevel.GROUP_T4_LARGE: TIER_4_RATES,
    NeonMembershipLevel.GROUP_T4_UNLIMITED: TIER_4_RATES,
    # HeyCounsel — mirror the matching individual tier
    NeonMembershipLevel.HEYCOUNSEL_T1: TIER_1_RATES,
    NeonMembershipLevel.HEYCOUNSEL_T2: TIER_2_RATES,
    NeonMembershipLevel.HEYCOUNSEL_T3: TIER_3_RATES,
    NeonMembershipLevel.HEYCOUNSEL_T4: TIER_4_RATES,
}

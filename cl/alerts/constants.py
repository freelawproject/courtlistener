from cl.alerts.models import Alert
from cl.donate.models import NeonMembershipLevel

# Free Law Project membership URLs, shared by the alert creation form and the
# Search Alerts API for membership upsell messaging. The upgrade URL is a base
# path; callers append the user's Neon membership id.
FLP_MEMBERSHIP_URL = "https://free.law/membership/"
MEMBERSHIP_UPGRADE_BASE_URL = (
    "https://donate.free.law/constituent/memberships/upgrade/"
)
# Legacy memberships can't be upgraded through Neon's standard flow; sending
# them to MEMBERSHIP_UPGRADE_BASE_URL 404s (see #7136). Route them to a help
# page that explains how to get more features instead (e.g. cancel the legacy
# membership and join again).
LEGACY_MEMBERSHIP_HELP_URL = "https://wiki.free.law/c/courtlistener/help/memberships/individual-memberships/legacy-memberships"

RECAP_ALERT_QUOTAS = {
    Alert.REAL_TIME: {
        "free": 0,
        NeonMembershipLevel.LEGACY: 0,
        NeonMembershipLevel.TIER_1: 5,
        NeonMembershipLevel.LSO_1: 5,
        NeonMembershipLevel.HEYCOUNSEL_T1: 5,
        NeonMembershipLevel.EDU: 5,
        NeonMembershipLevel.TIER_2: 10,
        NeonMembershipLevel.HEYCOUNSEL_T2: 10,
        NeonMembershipLevel.TIER_3: 25,
        NeonMembershipLevel.HEYCOUNSEL_T3: 25,
        NeonMembershipLevel.TIER_4: 50,
        NeonMembershipLevel.HEYCOUNSEL_T4: 50,
    },
    "other_rates": {
        "free": 5,
        NeonMembershipLevel.LEGACY: 5,
        NeonMembershipLevel.TIER_1: 10,
        NeonMembershipLevel.LSO_1: 10,
        NeonMembershipLevel.HEYCOUNSEL_T1: 10,
        NeonMembershipLevel.EDU: 10,
        NeonMembershipLevel.TIER_2: 25,
        NeonMembershipLevel.HEYCOUNSEL_T2: 25,
        NeonMembershipLevel.TIER_3: 50,
        NeonMembershipLevel.HEYCOUNSEL_T3: 50,
        NeonMembershipLevel.TIER_4: 100,
        NeonMembershipLevel.HEYCOUNSEL_T4: 100,
    },
}

from cl.alerts.models import Alert
from cl.donate.models import NeonMembershipLevel

RECAP_ALERT_QUOTAS = {
    Alert.REAL_TIME: {
        "free": 0,
        NeonMembershipLevel.LEGACY: 0,
        NeonMembershipLevel.TIER_1: 5,
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

from cl.alerts.models import Alert
from cl.donate.models import NeonMembership

RECAP_ALERT_QUOTAS = {
    Alert.REAL_TIME: {
        "free": 0,
        NeonMembership.LEGACY: 0,
        NeonMembership.TIER_1: 5,
        NeonMembership.EDU: 5,
        NeonMembership.TIER_2: 10,
        NeonMembership.TIER_3: 25,
        NeonMembership.TIER_4: 50,
    },
    "other_rates": {
        "free": 5,
        NeonMembership.LEGACY: 5,
        NeonMembership.TIER_1: 10,
        NeonMembership.EDU: 10,
        NeonMembership.TIER_2: 25,
        NeonMembership.TIER_3: 50,
        NeonMembership.TIER_4: 100,
    },
}

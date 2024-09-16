import environ

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)

# Payment secrets
EIN_SECRET = env("EIN_SECRET", default="")

# Payments & Prices
MIN_DONATION = {
    "rt_alerts": 10,
    "docket_alerts": 5,
}
MAX_FREE_DOCKET_ALERTS = 5
UNLIMITED_DOCKET_ALERT_EMAIL_DOMAINS = env.list(
    "UNLIMITED_DOCKET_ALERT_EMAIL_DOMAINS", default=[]
)
DOCKET_ALERT_RECAP_BONUS = 10
MAX_ALERT_RESULTS_PER_DAY = 30

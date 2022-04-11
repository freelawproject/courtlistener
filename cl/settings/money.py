import environ

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)

FUNDRAISING_MODE = env("FUNDRAISING_MODE", default=False)


#####################
# Payments & Prices #
#####################
from datetime import date

MIN_DONATION = {
    "rt_alerts": 10,
    "docket_alerts": 5,
}
MAX_FREE_DOCKET_ALERTS = 5
DOCKET_ALERT_RECAP_BONUS = 10
MAX_ALERT_RESULTS_PER_DAY = 30
# If people pay via XERO invoices, this is the ID we see in our stripe
# callbacks
XERO_APPLICATION_ID = "ca_1pvP3rYcArUkd3InUnImFI9llOiSIq6k"


# Payment secrets
EIN_SECRET = env("EIN_SECRET", default="")

PAYPAL_ENDPOINT = env(
    "PAYPAL_ENDPOINT", default="https://api.sandbox.paypal.com"
)
PAYPAL_ACCOUNT = env("PAYPAL_ACCOUNT", default="donate@free.law")
PAYPAL_CLIENT_ID = ""
PAYPAL_SECRET_KEY = ""
STRIPE_SECRET_KEY = ""
STRIPE_PUBLIC_KEY = ""


# Key for Follow the Money API
FTM_KEY = env("FTM_KEY", default="")
FTM_LAST_UPDATED = env("FTM_LAST_UPDATED", default=date.today())

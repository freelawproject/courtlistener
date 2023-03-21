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

# If people pay via XERO invoices, this is the ID we see in our stripe
# callbacks
XERO_APPLICATION_ID = "ca_1pvP3rYcArUkd3InUnImFI9llOiSIq6k"


if DEVELOPMENT:
    PAYPAL_ENDPOINT = "https://api.sandbox.paypal.com"
    PAYPAL_ACCOUNT = "donate-facilitator@free.law"
    PAYPAL_CLIENT_ID = env("PAYPAL_DEV_CLIENT_ID", default="")
    PAYPAL_SECRET_KEY = env("PAYPAL_DEV_SECRET_KEY", default="")
    STRIPE_SECRET_KEY = env("STRIPE_DEV_SECRET_KEY", default="")
    STRIPE_PUBLIC_KEY = env("STRIPE_DEV_PUBLIC_KEY", default="")
else:
    PAYPAL_ENDPOINT = "https://api.paypal.com"
    PAYPAL_ACCOUNT = "donate@free.law"
    PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID", default="")
    PAYPAL_SECRET_KEY = env("PAYPAL_SECRET_KEY", default="")
    STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
    STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", default="")

import environ

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)


#########
# Email #
#########
if DEVELOPMENT:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    BASE_BACKEND = EMAIL_BACKEND
else:
    EMAIL_BACKEND = "cl.lib.email_backends.EmailBackend"
    BASE_BACKEND = "django_ses.SESBackend"
    AWS_SES_REGION_NAME = "us-west-2"
    AWS_SES_REGION_ENDPOINT = "email.us-west-2.amazonaws.com"

# Max email attachment to send in bytes, 350KB
MAX_ATTACHMENT_SIZE = 350_000

SERVER_EMAIL = "CourtListener <noreply@courtlistener.com>"
DEFAULT_FROM_EMAIL = "CourtListener <noreply@courtlistener.com>"
DEFAULT_ALERTS_EMAIL = "CourtListener Alerts <alerts@courtlistener.com>"
SCRAPER_ADMINS = (
    ("Slack Juriscraper Channel", "j9f4b5n5x7k8x2r1@flp-talk.slack.com"),
    ("PA", "arderyp@protonmail.com"),
)

# Mailchimp secret (used for webhook URLs)
MAILCHIMP_SECRET = env("MAILCHIMP_SECRET", default="")
MAILCHIMP_API_KEY = env("MAILCHIMP_API_KEY", default="")

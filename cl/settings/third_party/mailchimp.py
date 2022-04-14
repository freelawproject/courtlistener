import environ

env = environ.FileAwareEnv()


# Mailchimp secret (used for webhook URLs)
MAILCHIMP_SECRET = env("MAILCHIMP_SECRET", default="")
MAILCHIMP_API_KEY = env("MAILCHIMP_API_KEY", default="")

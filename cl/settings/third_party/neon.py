import environ

env = environ.FileAwareEnv()

NEON_API_URL = env("NEON_API_URL", default="https://api.neoncrm.com/v2")

# Base URL of the Neon CRM admin UI, used to build links to Neon records.
NEON_ADMIN_URL = env("NEON_ADMIN_URL", default="https://donate.free.law/admin")

NEON_ORG_ID = env("NEON_ORG_ID", default="")
NEON_API_KEY = env("NEON_API_KEY", default="")
NEON_AUTHORIZATION_TOKEN = env("NEON_AUTHORIZATION_TOKEN", default="")
NEON_MAX_WEBHOOK_NUMBER = env("NEON_MAX_WEBHOOK_NUMBER", default=100)

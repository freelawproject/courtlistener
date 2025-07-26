import environ

env = environ.FileAwareEnv()

BLOCKED_DOMAINS = {
    "passinbox.com",  # Used for API abuse
}


# 1: Every email bounce/complaint is stored.
# 0.5: Half email bounces/complaints are stored.
# 0.1: 10% of email bounces/complaints are stored.
# 0: No email bounces/complaints are stored.
BOUNCES_STORE_RATE = env.float("BOUNCES_STORE_RATE", default=0)
COMPLAINTS_STORE_RATE = env.float("COMPLAINTS_STORE_RATE", default=0)

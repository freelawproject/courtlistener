import environ

env = environ.FileAwareEnv()

MAINTENANCE_MODE_ENABLED = env.bool("MAINTENANCE_MODE_ENABLED", default=False)
MAINTENANCE_MODE_ALLOW_STAFF = env.bool(
    "MAINTENANCE_MODE_ALLOW_STAFF",
    default=True,
)

MAINTENANCE_MODE = {
    "enabled": MAINTENANCE_MODE_ENABLED,
    "allow_staff": MAINTENANCE_MODE_ALLOW_STAFF,
}

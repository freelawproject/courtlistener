import environ

env = environ.FileAwareEnv()
IQUERY_CASE_PROBE_DAEMON_ENABLED = env.bool(
    "IQUERY_CASE_PROBE_DAEMON_ENABLED", default=False
)
IQUERY_PROBE_MAX_OFFSET = env.int("IQUERY_PROBE_MAX_OFFSET", default=400)
IQUERY_MAX_PROBE = env.int("IQUERY_MAX_PROBE", default=32)
IQUERY_PROBE_WAIT = env.int("IQUERY_PROBE_WAIT", default=300)
IQUERY_COURT_BLOCKED_WAIT = env.int("IQUERY_COURT_BLOCKED_WAIT", default=600)
IQUERY_COURT_BLOCKED_MAX_ATTEMPTS = env.int(
    "IQUERY_COURT_BLOCKED_MAX_ATTEMPTS", default=6
)
IQUERY_EMPTY_PROBES_LIMIT_HOURS = env.dict(
    "IQUERY_EMPTY_PROBES_LIMIT_HOURS",
    default={
        "default": 60,  # 60 hours
        "nmib": 8760,  # 1 year
        "vib": 1140,  # 2 months
    },
)
IQUERY_SWEEP_UPLOADS_SIGNAL_ENABLED = env.bool(
    "IQUERY_SWEEP_UPLOADS_SIGNAL_ENABLED", default=False
)
IQUERY_COURT_RATE = env("IQUERY_COURT_RATE", default="100/s")

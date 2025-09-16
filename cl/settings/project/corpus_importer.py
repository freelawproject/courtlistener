import environ

env = environ.FileAwareEnv()
IQUERY_CASE_PROBE_DAEMON_ENABLED = env.bool(
    "IQUERY_CASE_PROBE_DAEMON_ENABLED", default=False
)
IQUERY_PROBE_MAX_OFFSET = env.int("IQUERY_PROBE_MAX_OFFSET", default=400)
IQUERY_FIXED_SWEEP = env.int("IQUERY_FIXED_SWEEP", default=100)
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
        "akd": 120,  # 5 days
        "gub": 1080,  # 45 days
        "gud": 240,  # 10 days
        "med": 120,  # 5 days
        "ndb": 120,  # 5 days
        "nhd": 120,  # 5 days
        "nmid": 1080,  # 45 days
        "nmib": 8760,  # 1 year
        "vib": 1440,  # 2 months
        "vtd": 120,  # 5 days
        "wvnb": 120,  # 5 days
    },
)
IQUERY_SWEEP_UPLOADS_SIGNAL_ENABLED = env.bool(
    "IQUERY_SWEEP_UPLOADS_SIGNAL_ENABLED", default=False
)
IQUERY_COURT_RATE = env("IQUERY_COURT_RATE", default="100/s")

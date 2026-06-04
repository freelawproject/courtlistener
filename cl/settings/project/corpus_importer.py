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

# SCOTUS docket probing daemon
SCOTUS_PROBE_DAEMON_ENABLED = env.bool(
    "SCOTUS_PROBE_DAEMON_ENABLED", default=True
)
SCOTUS_PROBE_WAIT = env.int("SCOTUS_PROBE_WAIT", default=3600)
SCOTUS_PROBE_MAX_OFFSET = env.int("SCOTUS_PROBE_MAX_OFFSET", default=100)
SCOTUS_COURT_BLOCKED_WAIT = env.int("SCOTUS_COURT_BLOCKED_WAIT", default=600)
SCOTUS_COURT_BLOCKED_MAX_ATTEMPTS = env.int(
    "SCOTUS_COURT_BLOCKED_MAX_ATTEMPTS", default=6
)
SCOTUS_EMPTY_PROBES_LIMIT_HOURS = env.int(
    "SCOTUS_EMPTY_PROBES_LIMIT_HOURS", default=48
)
# Seconds the daemon pauses after a fetch timeout before retrying ingestion.
SCOTUS_TIMEOUT_WAIT = env.int("SCOTUS_TIMEOUT_WAIT", default=300)
# Seconds to sleep between sequential backfill HTTP fetches.
SCOTUS_BACKFILL_REQUEST_DELAY = env.float(
    "SCOTUS_BACKFILL_REQUEST_DELAY", default=1.0
)
# Cap on serials ingested per daemon iteration when catching up to a known
# watermark (operator-seeded highest_observed, or any large observed/ingested
# gap). Bounds the load placed on supremecourt.gov; the daemon trickles
# through the backlog over many iterations and falls back to probe mode once
# highest_ingested catches up to highest_observed.
SCOTUS_FIXED_SWEEP = env.int("SCOTUS_FIXED_SWEEP", default=100)
# Geometric step cap for the SCOTUS forward probe.
SCOTUS_MAX_PROBE = env.int("SCOTUS_MAX_PROBE", default=16)

OPENAI_TRANSCRIPTION_KEY = env("OPENAI_TRANSCRIPTION_KEY", default=None)

# Audio re-enqueue daemon. Acts as the rate limiter for OpenAI Whisper
# calls — process_audio_file no longer hands off to dispatch_transcribe,
# so this daemon is the only path that enqueues transcription tasks.
# Throughput cap = AUDIO_REENQUEUE_MAX_PER_SWEEP / AUDIO_REENQUEUE_WAIT.
AUDIO_REENQUEUE_DAEMON_ENABLED = env.bool(
    "AUDIO_REENQUEUE_DAEMON_ENABLED", default=False
)
AUDIO_REENQUEUE_WAIT = env.int("AUDIO_REENQUEUE_WAIT", default=60)
AUDIO_REENQUEUE_MAX_PER_SWEEP = env.int(
    "AUDIO_REENQUEUE_MAX_PER_SWEEP", default=5
)

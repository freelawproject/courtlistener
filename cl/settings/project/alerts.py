import environ

env = environ.FileAwareEnv()

##########################
# Scheduled alert hits   #
##########################
# How many ScheduledAlertHit rows go into each INSERT when a percolated
# document's hits are written. Each in-flight row costs roughly 100 KiB while
# psycopg builds the statement's parameter array, so 100 bounds that at ~10 MiB
# regardless of how many alerts one document matches. None sends them all in
# one statement.
SCHEDULED_ALERT_HIT_BATCH_SIZE = env.int(
    "SCHEDULED_ALERT_HIT_BATCH_SIZE", default=100
)

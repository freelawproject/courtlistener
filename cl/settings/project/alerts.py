import environ

env = environ.FileAwareEnv()

##########################
# Scheduled alert hits   #
##########################
# How many ScheduledAlertHit rows go into each INSERT when a percolated
# document's hits are written. None sends them all in one statement.
_scheduled_alert_hit_batch_size = env.str(
    "SCHEDULED_ALERT_HIT_BATCH_SIZE", default=""
)
SCHEDULED_ALERT_HIT_BATCH_SIZE = (
    int(_scheduled_alert_hit_batch_size)
    if _scheduled_alert_hit_batch_size
    else None
)

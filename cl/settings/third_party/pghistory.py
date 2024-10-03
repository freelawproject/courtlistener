# Default pghistory trackers for @pghistory.track()
import pghistory

PGHISTORY_DEFAULT_TRACKERS = (
    pghistory.UpdateEvent(
        condition=pghistory.AnyChange(exclude_auto=True), row=pghistory.Old
    ),
    pghistory.DeleteEvent(),
)

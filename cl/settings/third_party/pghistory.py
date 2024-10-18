# Default pghistory trackers for @pghistory.track()
import pghistory
from pghistory.admin.core import (
    BackFilter,
    EventModelFilter,
    LabelFilter,
    MethodFilter,
    ObjFilter,
)


class EventsAdminNoFilters(pghistory.admin.EventsAdmin):
    """Disable filters, except when looking at the events of a single object.

    In combination with `PGHISTORY_ADMIN_ALL_EVENTS = False`
    it causes the Events admin page to make no queries, except
    when looking at a single object's history, preventing
    useless DB hits
    """

    def get_list_filter(self, request):
        filters = []
        if "obj" in request.GET:
            filters = [
                LabelFilter,
                EventModelFilter,
                MethodFilter,
                ObjFilter,
                BackFilter,
            ]

        return filters


PGHISTORY_DEFAULT_TRACKERS = (
    pghistory.UpdateEvent(
        condition=pghistory.AnyChange(exclude_auto=True), row=pghistory.Old
    ),
    pghistory.DeleteEvent(),
)

# Disable the page with all Pghistory events, this page
# will only be viewable with filters
PGHISTORY_ADMIN_ALL_EVENTS = False
PGHISTORY_ADMIN_CLASS = EventsAdminNoFilters

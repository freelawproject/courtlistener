import pghistory
from pghistory.admin.core import (
    BackFilter,
    EventModelFilter,
    LabelFilter,
    MethodFilter,
    ObjFilter,
)
from pghistory.config import admin_model


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

    def get_queryset(self, request):
        # Run query only when we have a model name and object id in url. e.g.
        # obj=search.RECAPDocument:372557163
        if "obj" in request.GET:
            obj = request.GET.get("obj")
            if ":" in obj:
                obj_id = obj.split(":")[1]
                pgh_model = obj.split(":")[0]
                return admin_model().objects.filter(
                    pgh_obj_model=pgh_model, pgh_obj_id=obj_id
                )

        # By default it wont perform any query
        return admin_model().objects.none()


# Default pghistory trackers for @pghistory.track()
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

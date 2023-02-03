from django.db.models import F

from cl.lib.bot_detector import is_bot
from cl.lib.model_helpers import suppress_autotime


def increment_view_count(obj, request):
    """Increment the view count of an object in the DB

    Three tricks in this simple function:

      1. If it's a robot viewing the page, don't increment.
      2. Make sure not to update the "date_modified" fields.
      3. Do this using an atomic DB query for performance and don't reload from
         the database after the increment (which would take another query).

    :param obj: A django object containing a view_count parameter
    :param request: A django request so we can detect if it's a bot
    :return: Nothing. The obj is passed by reference
    """
    if not is_bot(request):
        cached_value = obj.view_count

        with suppress_autotime(obj, ["date_modified"]):
            obj.view_count = F("view_count") + 1
            obj.save(update_fields=["view_count"])

        # To get the new value, you either need to get the item from the DB a
        # second time, or just manipulate it manually....
        obj.view_count = cached_value + 1

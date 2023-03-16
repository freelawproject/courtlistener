import pgtrigger
from pghistory import trigger
from pghistory.core import DatabaseTracker, _get_name_from_label


class CustomSnapshot(DatabaseTracker):
    """Custom database tracker that allows you to save OLD data when you
    perform an update, when you perform an insert it saves NEW data

    Also ensures that no duplicated data is created when you perform a save
    without making a change with a model that contains auto_now fields

    This code is a copy from pghistory.core.Snapshot
    """

    def __init__(self, label=None):
        return super().__init__(label=label)

    def setup(self, event_model):
        insert_trigger = trigger.Event(
            event_model=event_model,
            label=self.label,
            name=_get_name_from_label(f"{self.label}_insert"),
            snapshot="NEW",
            when=pgtrigger.After,
            operation=pgtrigger.Insert,
        )

        # We exclude fields with auto_now to avoid duplicate data if we save
        # without making any modification, field value still will be saved
        # unless you exclude it

        event_fields = [
            field.name
            for field in event_model._meta.fields
            if not field.name.startswith("pgh_")
            and not hasattr(field, "auto_now")
        ]

        tracked_fields = [
            field.name
            for field in event_model.pgh_tracked_model._meta.fields
            if not hasattr(field, "auto_now")
        ]

        if set(event_fields) == set(tracked_fields):
            condition = pgtrigger.Condition("OLD.* IS DISTINCT FROM NEW.*")
        else:
            condition = pgtrigger.Q()
            for field in event_fields:
                if hasattr(event_model.pgh_tracked_model, field):
                    condition |= pgtrigger.Q(
                        **{f"old__{field}__df": pgtrigger.F(f"new__{field}")}
                    )

        # Use OLD instead of NEW to store previous value instead of new
        update_trigger = trigger.Event(
            event_model=event_model,
            label=self.label,
            name=_get_name_from_label(f"{self.label}_update"),
            snapshot="OLD",
            when=pgtrigger.After,
            operation=pgtrigger.Update,
            condition=condition,
        )

        pgtrigger.register(insert_trigger, update_trigger)(
            event_model.pgh_tracked_model
        )

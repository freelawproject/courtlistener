import pgtrigger
from pghistory import trigger
from pghistory.core import DatabaseTracker, _get_name_from_label


class AfterUpdateOrDeleteSnapshot(DatabaseTracker):
    """Custom database tracker that allows you to save OLD data when you do an
    update and avoid duplicates

    Optionally, you can decide whether the auto_now fields should affect the
    decision to create new rows or not

    This code is partially a copy from pghistory.core.Snapshot
    """

    label = "update_or_delete_snapshot"

    @staticmethod
    def prepare_event_fields(event_model, ignore_auto_now_fields):
        """Prepare list of event model fields to use in the trigger condition
        to trigger it
        :param event_model: event model generated from tracked model
        :param ignore_auto_now_fields: true if we should ignore auto_now fields
        to check if field value changed
        :return: list of valid fields to build the compare clause
        """
        if ignore_auto_now_fields:
            return [
                field.name
                for field in event_model._meta.fields
                if not field.name.startswith("pgh_")
                and not getattr(field, "auto_now", False)
            ]

        return [
            field.name
            for field in event_model._meta.fields
            if not field.name.startswith("pgh_")
        ]

    def __init__(self, label=None, ignore_auto_now_fields=False):
        # if set to true, all auto_now fields will be excluded in trigger
        # comparison to check if row changed
        self.ignore_auto_now_fields = ignore_auto_now_fields
        return super().__init__(label=label)

    def setup(self, event_model):
        # We only process fields from event model because they may or may
        # not contain all the fields of the tracked model
        event_fields = self.prepare_event_fields(
            event_model, self.ignore_auto_now_fields
        )

        tracked_fields = [
            field.name for field in event_model.pgh_tracked_model._meta.fields
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

        # Handle delete event
        delete_trigger = trigger.Event(
            event_model=event_model,
            label=self.label,
            name=_get_name_from_label(f"{self.label}_delete"),
            snapshot="OLD",
            when=pgtrigger.After,
            operation=pgtrigger.Delete,
            condition=None,
        )

        pgtrigger.register(update_trigger, delete_trigger)(
            event_model.pgh_tracked_model
        )

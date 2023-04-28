import pgtrigger
from pghistory.core import Changed, Snapshot


class AfterUpdateOrDeleteSnapshot(Snapshot):
    """Custom database tracker that allows you to save OLD data when you do
    an update, also will save OLD data when you do a delete action, it will
    also exclude auto_now fields like: date_modified

    Usage example:

    @pghistory.track(AfterUpdateOrDeleteSnapshot())

    """

    label = "update_or_delete_snapshot"

    def setup(self, event_model):
        # Fields that should be excluded from the comparison of old and new
        fields_to_exclude = [
            f.name
            for f in event_model.pgh_tracked_model._meta.fields
            if getattr(f, "auto_now", False)
        ]

        # Add update trigger with custom condition
        self.add_event_trigger(
            event_model=event_model,
            label=self.label,
            name=f"{self.label}_update",
            snapshot="OLD",
            when=pgtrigger.After,
            operation=pgtrigger.Update,
            condition=Changed(event_model, exclude=fields_to_exclude),
        )

        # Add delete trigger
        self.add_event_trigger(
            event_model=event_model,
            label=self.label,
            name=f"{self.label}_delete",
            snapshot="OLD",
            when=pgtrigger.After,
            operation=pgtrigger.Delete,
        )

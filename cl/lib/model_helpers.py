from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename


def make_recap_path(instance, filename):
    """Make a path to a good location on the local system for RECAP files.

    This dumps them all into the same directory, which seems to be OK, at least
    so far.
    """
    return "recap/%s" % get_valid_filename(filename)


def make_upload_path(instance, filename):
    """Return a string like pdf/2010/08/13/foo_v._var.pdf

    This function requires that when you save an item you provide an attribute
    called file_with_date on the object. That date will be used to place the
    item in the correct location on disk.
    """
    try:
        # Cannot do proper type checking here because of circular import
        # problems when importing Audio, Document, etc.
        d = instance.file_with_date
    except AttributeError:
        raise NotImplementedError("This function cannot be used without a "
                                  "file_with_date attribute.")

    return '%s/%s/%02d/%02d/%s' % (
        filename.split('.')[-1],
        d.year,
        d.month,
        d.day,
        get_valid_filename(filename)
    )


def validate_partial_date(instance, fields):
    """Ensure that partial dates make sense.

    Validates that:
     - Both granularity and date field are either completed or empty (one cannot
       be completed if the other is not).
     - If a partial date, the day/month is/are set to 01.
    """
    from cl.people_db.models import GRANULARITY_MONTH, GRANULARITY_YEAR
    for field in fields:
        d = getattr(instance, 'date_%s' % field)
        granularity = getattr(instance, 'date_granularity_%s' % field)

        if any([d, granularity]) and not all([d, granularity]):
            raise ValidationError({
                'date_%s' % field: 'Date and granularity must both be complete '
                                   'or blank. Hint: The values are: date: %s, '
                                   'granularity: %s' % (d, granularity)
            })

        # If a partial date, are days/month set to 1?
        bad_date = False
        if granularity == GRANULARITY_YEAR:
            if d.month != 1 and d.day != 1:
                bad_date = True
        if granularity == GRANULARITY_MONTH:
            if d.day != 1:
                bad_date = True
        if bad_date:
            raise ValidationError({
                'date_%s' % field: 'Granularity was set as partial, but date '
                                   'appears to include month/day other than 1.'
            })


def validate_is_not_alias(instance, fields):
    """Ensure that an alias to an object is not being used instead of the object
    itself.

    Requires that the object have an is_alias property or attribute.
    """
    for field in fields:
        referenced_object = getattr(instance, field)
        if referenced_object is not None and referenced_object.is_alias:
            raise ValidationError({
                field: 'Cannot set "%s" field to an alias of a "%s". Hint: '
                       '"%s" is an alias of "%s"' % (
                    field,
                    type(referenced_object).__name__,
                    referenced_object,
                    referenced_object.is_alias_of
                )
            })


def validate_has_full_name(instance):
    """This ensures that blank values are not passed to the first and last name
    fields. Normally this can be done by the DB layer, but people could still
    pass blank strings through, and this blocks even that.
    """
    if not all([instance.name_first, instance.name_last]):
        raise ValidationError(
            "Both first and last names are required."
        )


def validate_nomination_fields_ok(instance):
    """Validate a few things:
     - date_nominated and date_elected cannot both have values
     - if nominated, then date_elected not complete and vice versa.
    """
    if instance.date_nominated and instance.date_elected:
        raise ValidationError(
            "Cannot have both a date nominated and a date elected."
        )

    if instance.how_selected:
        selection_type_group = instance.SELECTION_METHOD_GROUPS[instance.how_selected]
        if selection_type_group == 'Election' and instance.date_nominated:
            raise ValidationError(
                "Cannot have a nomination date for a position with how_selected of "
                "%s" % instance.get_how_selected_display()
            )
        if selection_type_group == 'Appointment' and instance.date_elected:
            raise ValidationError(
                "Cannot have an election date for a position with how_selected of "
                "%s" % instance.get_how_selected_display()
            )


def validate_supervisor(instance):
    """Ensure that the supervisor field makes sense.

     - Supervisors can only be judges.
     - Supervisor field can only be completed when the position is that of a
       clerk.
    """
    sup = instance.supervisor
    if sup:
        if not sup.is_judge:
            raise ValidationError(
                {'supervisor': "The supervisor field can only be set to a "
                               "judge, but '%s' does not appear to have ever "
                               "been a judge." % sup.name_full
                 }
            )

    if sup and not instance.is_clerkship:
        raise ValidationError(
            "You have configured a supervisor for this field ('%s'), but it "
            "the position_type is not a clerkship. Instead it's: '%s'" % (
                sup.name_full,
                instance.position_type,
            )
        )


def validate_all_or_none(instance, fields):
    """Ensure that all fields are complete or that none are complete"""
    num_fields = len(fields)
    completed_fields = sum(1 for f in fields if
                           getattr(instance, f) or
                           getattr(instance, f) == 0)
    all_complete = completed_fields == num_fields
    none_complete = completed_fields == 0
    if not any([all_complete, none_complete]):
        raise ValidationError(
            "%s of the following fields are complete, but either all of them need to be, or none of them need to be: %s" % (
                completed_fields,
                ", ".join(fields),
            )
        )


def validate_exactly_n(instance, n, fields):
    """Ensure that exactly n of the fields has a value."""
    completed_fields = sum(1 for f in fields if getattr(instance, f))
    if completed_fields != n:
        raise ValidationError(
            "Exactly %s of the following fields can be completed (currently "
            "%s are): %s" % (n, completed_fields, ", ".join(fields))
        )


def validate_at_most_n(instance, n, fields):
    """Ensure that at most n fields are complete."""
    completed_fields = sum(1 for f in fields if getattr(instance, f))
    if completed_fields > n:
        raise ValidationError(
                "Exactly %s of the following fields can be completed (currently "
                "%s are): %s" % (n, completed_fields, ", ".join(fields))
        )


def validate_not_all(instance, fields):
    """Make sure that all of the passed fields are not complete."""
    num_fields = len(fields)
    num_completed_fields = sum(1 for f in fields if getattr(instance, f))
    if num_completed_fields == num_fields:
        # They're all completed. Boo!
        raise ValidationError(
            "All of the following fields cannot be completed: %s" %
            ', '.join(fields)
        )


def make_choices_group_lookup(c):
    """Invert a choices variable in a model to get the group name for a
    tuple.
    """
    d = {}
    for choice, value in c:
        if isinstance(value, (list, tuple)):
            for t in value:
                d[t[0]] = choice
        else:
            d[choice] = value
    return d


def disable_auto_now_fields(*models):
    """Turns off the auto_now and auto_now_add attributes on a Model's fields,
    so that an instance of the Model can be saved with a custom value.

    Based on: https://stackoverflow.com/questions/7499767/temporarily-disable-auto-now-auto-now-add
    """
    for model in models:
        # noinspection PyProtectedMember
        for field in model._meta.local_fields:
            if hasattr(field, 'auto_now'):
                field.auto_now = False
            if hasattr(field, 'auto_now_add'):
                field.auto_now_add = False

from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename


def make_recap_path(instance, filename):
    """Make a path to a good location on the local system for RECAP files."""
    raise NotImplementedError("Need to do research based on the files that are "
                              "returned to establish a sane practice here.")


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


def validate_partial_date(instance, field):
    """Ensure that partial dates make sense.

    Validates that:
     - Both granularity and date field are either completed or empty (one cannot
       be completed if the other is not).
     - If a partial date, the day/month is/are set to 01.
    """
    from cl.people_db.models import GRANULARITY_MONTH, GRANULARITY_YEAR
    d = getattr(instance, 'date_%s' % field)
    granularity = getattr(instance, 'date_granularity_%s' % field)

    if any([d, granularity]) and not all([d, granularity]):
        raise ValidationError({
            'date_%s' % field: 'Date and granularity must both be complete or '
                               'blank.'
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

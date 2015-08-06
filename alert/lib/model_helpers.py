from django.utils.text import get_valid_filename


def make_upload_path(instance, filename):
    """Return a string like pdf/2010/08/13/foo_v._var.pdf"""
    try:
        # Cannot do proper type checking here because of circular import
        # problems when importing Audio, Document, etc.
        if 'Audio' in str(type(instance)):
            d = instance.date_argued
        elif 'Document' in str(type(instance)):
            d = instance.date_filed
        else:
            raise NotImplementedError("This function cannot be used without "
                                      "custom work for new object types.")

    except AttributeError:
        # The date is unknown for the case. Use the time retrieved.
        d = instance.time_retrieved

    return '%s/%s/%02d/%02d/%s' % (
        filename.split('.')[-1],
        d.year,
        d.month,
        d.day,
        get_valid_filename(filename)
    )

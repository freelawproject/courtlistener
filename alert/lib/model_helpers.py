from django.utils.text import get_valid_filename


def make_upload_path(instance, filename):
    """Return a string like pdf/2010/08/13/foo_v._var.pdf, with the date set
    as the date_filed for the case."""
    # this code NOT cross platform. Use os.path.join or similar to fix.
    mimetype = filename.split('.')[-1] + '/'

    try:
        # Cannot do proper type checking here because of circular import problems
        # when importing Audio, Document, etc.
        if 'Audio' in str(type(instance)):
            path = mimetype + instance.date_argued.strftime("%Y/%m/%d/") + \
                   get_valid_filename(filename)
        elif 'Document' in str(type(instance)):
            path = mimetype + instance.date_filed.strftime("%Y/%m/%d/") + \
                   get_valid_filename(filename)
        else:
            raise NotImplementedError("This function cannot be used without custom work for new object types.")
    except AttributeError:
        # The date is unknown for the case. Use today's date.
        path = mimetype + instance.time_retrieved.strftime("%Y/%m/%d/") + \
               get_valid_filename(filename)
    return path

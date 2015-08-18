import errno
import os


class _UNSPECIFIED(object):
    pass

def deepgetattr(obj, name, default=_UNSPECIFIED):
    """Try to retrieve the given attribute of an object, digging on '.'.

    This is an extended getattr, digging deeper if '.' is found.

    Args:
        obj (object): the object of which an attribute should be read
        name (str): the name of an attribute to look up.
        default (object): the default value to use if the attribute wasn't found

    Returns:
        the attribute pointed to by 'name', splitting on '.'.

    Raises:
        AttributeError: if obj has no 'name' attribute.
    """
    try:
        if '.' in name:
            attr, subname = name.split('.', 1)
            return deepgetattr(getattr(obj, attr), subname, default)
        else:
            return getattr(obj, name)
    except AttributeError:
        if default is _UNSPECIFIED:
            raise
        else:
            return default

def mkdir_p(path):
    """Makes a directory path, but doesn't crash if the path already exists."""
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

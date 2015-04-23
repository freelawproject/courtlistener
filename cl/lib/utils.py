import errno
import os


def deepgetattr(obj, attr):
    """Recurse through an attribute chain to get the ultimate value."""
    return reduce(getattr, attr.split('.'), obj)


def mkdir_p(path):
    """Makes a directory path, but doesn't crash if the path already exists."""
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

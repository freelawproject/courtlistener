import collections
import errno
import os
import re
from itertools import chain, islice, tee
from typing import Any, List, Optional, Tuple

from django.db.models import QuerySet
from reporters_db import EDITIONS


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
        if "." in name:
            attr, subname = name.split(".", 1)
            return deepgetattr(getattr(obj, attr), subname, default)
        else:
            return getattr(obj, name)
    except AttributeError:
        if default is _UNSPECIFIED:
            raise
        else:
            return default


def mkdir_p(path):
    """Makes a directory path, but doesn't crash if the path already exists.

    Doesn't clobber.

    :param path: A path you wish to create on the file system.
    """
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            if os.path.isdir(path):
                pass
            else:
                raise OSError(
                    "Cannot create directory. Location already "
                    "exists, but is not a directory: %s" % path
                )
        else:
            raise


def chunks(iterable, chunk_size):
    """Like the chunks function, but the iterable can be a generator.

    Note that the chunks must be *consumed* for it to work properly. Usually
    that means converting them to a list in your loop.

    :param iterable: Any iterable
    :param chunk_size: The number of items to put in each chunk
    :return: Yields iterators of chunksize number of items from iterable
    """
    iterator = iter(iterable)
    for first in iterator:
        yield chain([first], islice(iterator, chunk_size - 1))


def previous_and_next(some_iterable):
    """Provide previous and next values while iterating a list.

    This is from: http://stackoverflow.com/a/1012089/64911

    This will allow you to lazily iterate a list such that as you iterate, you
    get a tuple containing the previous, current, and next value.
    """
    prevs, items, nexts = tee(some_iterable, 3)
    prevs = chain([None], prevs)
    nexts = chain(islice(nexts, 1, None), [None])
    return zip(prevs, items, nexts)


def is_iter(item):
    # See: http://stackoverflow.com/a/1952655/64911
    if isinstance(item, collections.Iterable):
        return True
    return False


def remove_duplicate_dicts(l):
    """Given a list of dicts, remove any that are the same.

    See: http://stackoverflow.com/a/9427216/64911
    """
    return [dict(t) for t in set([tuple(d.items()) for d in l])]


def alphanumeric_sort(query: QuerySet, sort_key: str) -> List[Any]:
    """Sort a django queryset by a particular field value

    :param query: The django queryset
    :param sort_key: The field to sort naturally
    :return:
    """
    convert = lambda text: int(text) if text.isdigit() else text
    alphanum_key = lambda key: [
        convert(c) for c in re.split("([0-9]+)", getattr(key, sort_key))
    ]
    return sorted(query, key=alphanum_key)


def find_reporters(reporter: str) -> Tuple[str, Optional[str]]:
    """A convenience method to find reporter from url slug

    :param EDITIONS: The reporter editions from reporters-db
    :param reporter: The reporter in the URL slug
    :return: The proper reporter string or original with root reporter if found
    """
    reporter_editions = EDITIONS.keys()
    reporter_editions = [
        rep.replace("(", "\\(").replace(")", "\\)")
        for rep in reporter_editions
    ]
    reporter_editions = [
        f"({rep.replace('.', '.?').replace(' ', ' ?-?')})"
        for rep in reporter_editions
    ]
    rep_regex_pattern = "|".join(reporter_editions)
    rep_regex = re.compile(r"^(%s)$" % rep_regex_pattern, re.I)
    m = re.match(rep_regex, reporter)
    if m and m.groups():
        g = m.groups()
        if g[0]:
            reporter = list(EDITIONS.keys())[g[1:].index(g[0])]
            root_reporter = EDITIONS.get(reporter)
            return reporter, root_reporter
    return reporter, None

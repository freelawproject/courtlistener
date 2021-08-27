import collections
import errno
import os
import re
from itertools import chain, islice, tee
from typing import Any, Iterable, List, Optional, Tuple, Union

from django.db.models import QuerySet


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


def human_sort(
    unordered_list: Iterable[Union[str, Tuple[str, Any]]],
    key: Optional[str] = None,
) -> Iterable[Union[str, Tuple[str, Any]]]:
    """Human sort Lists of strings or list of dictionaries

    :param unordered_list: The list we want to sort
    :param key: A key (if any) to sort the dictionary with.
    :return: An ordered list
    """
    convert = lambda text: int(text) if text.isdigit() else text
    if key:
        sorter = lambda item: [
            convert(c) for c in re.split("([0-9]+)", item[key])
        ]
    else:
        sorter = lambda item: [convert(c) for c in re.split("([0-9]+)", item)]

    return sorted(unordered_list, key=sorter)

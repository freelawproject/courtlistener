import re
from collections.abc import Iterable
from itertools import chain, islice, tee
from typing import Any
from typing import Iterable as IterableType
from typing import List, Optional, Tuple

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


def is_iter(item: Any) -> bool:
    # See: http://stackoverflow.com/a/1952655/64911
    if isinstance(item, Iterable):
        return True
    return False


def remove_duplicate_dicts(l):
    """Given a list of dicts, remove any that are the same.

    See: http://stackoverflow.com/a/9427216/64911
    """
    return [dict(t) for t in set([tuple(d.items()) for d in l])]


def human_sort(
    unordered_list: IterableType[str | Tuple[str, Any]],
    key: Optional[str] = None,
) -> IterableType[str | Tuple[str, Any]]:
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

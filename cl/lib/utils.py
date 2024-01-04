import re
from collections.abc import Iterable
from itertools import chain, islice, tee
from typing import Any
from typing import Iterable as IterableType
from typing import Optional, Tuple

from cl.lib.model_helpers import clean_docket_number, is_docket_number
from cl.lib.types import CleanData


class _UNSPECIFIED:
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


def chunks(iterable, chunk_size: int):
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
    return isinstance(item, Iterable)


def remove_duplicate_dicts(l: list[dict]) -> list[dict]:
    """Given a list of dicts, remove any that are the same.

    See: http://stackoverflow.com/a/9427216/64911
    """
    return [dict(t) for t in {tuple(d.items()) for d in l}]


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


def wrap_text(length: int, text: str) -> str:
    """Wrap text to specified length without cutting words

    :param length: max length to wrap
    :param text: text to wrap
    :return: text wrapped
    """
    words = text.split(" ")
    if words:
        lines = [words[0]]
        for word in words[1:]:
            if len(lines[-1]) + len(word) < length:
                lines[-1] += f" {word}"
            else:
                lines.append(word)
                break
        return " ".join(lines)
    return ""


def get_array_of_selected_fields(cd: CleanData, prefix: str) -> list[str]:
    """Gets the selected checkboxes from the form data, and puts it into
    an array. Uses a prefix to know which items to pull out of the cleaned
    data.Check forms.py to see how the prefixes are set up.
    """
    return [
        k.replace(prefix, "")
        for k, v in cd.items()
        if (k.startswith(prefix) and v is True)
    ]


def cleanup_main_query(query_string: str) -> str:
    """Enhance the query string with some simple fixes

     - Make any numerical queries into phrases (except dates)
     - Add hyphens to district docket numbers that lack them
     - Ignore tokens inside phrases
     - Handle query punctuation correctly by mostly ignoring it

    :param query_string: The query string from the form
    :return The enhanced query string
    """
    inside_a_phrase = False
    cleaned_items = []
    for item in re.split(r'([^a-zA-Z0-9_\-~":]+)', query_string):
        if not item:
            continue

        if item.startswith('"') or item.endswith('"'):
            # Start or end of a phrase; flip whether we're inside a phrase
            inside_a_phrase = not inside_a_phrase
            cleaned_items.append(item)
            continue

        if inside_a_phrase:
            # Don't do anything if we're already in a phrase query
            cleaned_items.append(item)
            continue

        not_numeric = not item[0].isdigit()
        is_date_str = re.match(
            "[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", item
        )
        if any([not_numeric, is_date_str]):
            cleaned_items.append(item)
            continue

        m = re.match(r"(\d{2})(cv|cr|mj|po)(\d{1,5})", item)
        if m:
            # It's a docket number missing hyphens, e.g. 19cv38374
            item = "-".join(m.groups())

        # Some sort of number, probably a docket number or other type of number
        # Wrap in quotes to do a phrase search
        if is_docket_number(item) and "docketNumber:" not in query_string:
            # Confirm is a docket number and clean it. So docket_numbers with
            # suffixes can be searched: 1:21-bk-1234-ABC -> 1:21-bk-1234,
            item = clean_docket_number(item)
            # Adds a proximity query of ~1 to match
            # numbers like 1:21-cv-1234 -> 21-1234
            cleaned_items.append(f'docketNumber:"{item}"~1')
        else:
            cleaned_items.append(f'"{item}"')

    return "".join(cleaned_items)

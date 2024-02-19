import re
from collections.abc import Iterable
from itertools import chain, islice, tee
from typing import Any
from typing import Iterable as IterableType
from typing import Match, Optional, Tuple

from django.core.cache import caches

import cl.search.models as search_model
from cl.lib.crypto import sha256
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
    """Warning: If you're considering using this method, you might want to
    consider using itertools.batched instead.
    Like the chunks function, but the iterable can be a generator.

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


def lookup_child_courts(parent_courts: list[str]) -> set[str]:
    """Recursively fetches child courts for the given parent courts.

    :param parent_courts: List of parent court_ids.
    :return: Set of all child court IDs.
    """

    cache = caches["db_cache"]
    all_child_courts = set()
    sorted_courts_hash = sha256("-".join(sorted(parent_courts)))
    cache_key = f"child_courts:{sorted_courts_hash}"
    cached_result = cache.get(cache_key)

    if cached_result is not None:
        return set(cached_result)

    child_courts = search_model.Court.objects.filter(
        parent_court_id__in=parent_courts
    ).values_list("id", flat=True)
    all_child_courts.update(child_courts)
    if not all_child_courts:
        return set()

    final_results = all_child_courts.union(
        lookup_child_courts(list(all_child_courts))
    )
    sorted_final_results = sorted(final_results)
    one_month = 60 * 60 * 24 * 30
    cache.set(cache_key, sorted_final_results, one_month)
    return set(sorted_final_results)


def get_child_court_ids_for_parents(selected_courts_string: str) -> str:
    """
    Retrieves and combines court IDs from both the given parents and their
    child courts and removing duplicates.

    :param selected_courts_string: The courts from the original user query.
    :return: A string containing the unique combination of parent and child courts.
    """
    unique_courts = set(re.findall(r'"(.*?)"', selected_courts_string))
    unique_courts.update(lookup_child_courts(list(unique_courts)))
    courts = [f'"{c}"' for c in sorted(list(unique_courts))]
    return " OR ".join(courts)


def extend_child_courts(match: Match[str]) -> str:
    """Extends court_id: queries with their child courts.

    :param match: A regex match object containing the matched court_id: query.
    :return: A string with the court_id query extended with child courts.
    """

    # Remove parentheses
    cleaned_str = re.sub(r"[()]", "", match.group(1))
    # Split the string by spaces to handle each court
    courts = cleaned_str.split()
    # Wrap each word in double quotes, except for 'OR'
    formatted_courts = [
        f'"{court}"' if court != "OR" else court for court in courts
    ]
    query_content = " ".join(formatted_courts)
    return f"court_id:({get_child_court_ids_for_parents(query_content)})"


def modify_court_id_queries(query_str: str) -> str:
    """Modify 'court_id' values in a query string.

    Parses valid 'court_id:' values in the string:
    - "court_id:" followed by a single word without spaces:
        court_id:cabc
    - "court_id:" followed by a list of words separated by "OR", wrapped in
    parentheses:
        court_id:(cabc OR nysupctnewyork)

    For each valid 'court_id' query, it retrieves the courts and extends them
    with their child courts, then reinserts them back into the original
    query string.

    :param query_str: The query string to be parsed.
    :return: The modified query string after extending with child courts, or
    the original query string if no valid 'court_id:' queries are found.
    """

    pattern = r"court_id:(\w+|\(\w+(?:\sOR\s\w+)*\))"
    modified_query = re.sub(pattern, extend_child_courts, query_str)
    return modified_query


def cleanup_main_query(query_string: str) -> str:
    """Enhance the query string with some simple fixes

     - Make any numerical queries into phrases (except dates)
     - Add hyphens to district docket numbers that lack them
     - Ignore tokens inside phrases
     - Handle query punctuation correctly by mostly ignoring it
     - Capture "court_id:court" queries, retrieve the child courts for each
     court in the query, append them, and then add them back to the original
     query.

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

    cleaned_query = "".join(cleaned_items)
    # If it's a court_id query, parse it, append the child courts, and then
    # reintegrate them into the original query.
    final_query = modify_court_id_queries(cleaned_query)
    return final_query


def check_for_proximity_tokens(query: str) -> bool:
    """Check whether the query contains an unrecognized proximity token from
    other common search providers.

    :param query: The input query string
    :return: True if the query contains an unrecognized proximity token.
    Otherwise False
    """

    return "/s" in query or "/p" in query


def check_unbalanced_parenthesis(query: str) -> bool:
    """Check whether the query string has unbalanced opening or closing
    parentheses.

    :param query: The input query string
    :return: True if the query contains unbalanced parenthesis. Otherwise False
    """
    opening_count = query.count("(")
    closing_count = query.count(")")

    return opening_count != closing_count


def check_unbalanced_quotes(query: str) -> bool:
    """Check whether the query string has unbalanced quotes.

    :param query: The input query string
    :return: True if the query contains unbalanced quotes. Otherwise False
    """
    quotes_count = query.count('"')
    return quotes_count % 2 != 0


def remove_last_symbol_occurrence(
    query: str, symbol_count: int, symbol: str
) -> tuple[str, int]:
    """Remove the last occurrence of a specified symbol from a query string and
     update the symbol count.

    :param query: The query string.
    :param symbol_count: The current count of the symbol in the query.
    :param symbol: The symbol to be removed from the query.
    :return: A tuple containing the updated query string and the updated symbol
     count.
    """
    # Find last unclosed symbol position.
    last_symbol_pos = query.rfind(symbol)
    # Remove the last symbol from the query.
    query = query[:last_symbol_pos] + query[last_symbol_pos + 1 :]
    # Update the symbol count.
    symbol_count -= 1
    return query, symbol_count


def sanitize_unbalanced_parenthesis(query: str) -> str:
    """Sanitize a query by removing unbalanced opening or closing parentheses.

    :param query: The input query string
    :return: The sanitized query string, after removing unbalanced parentheses.
    """
    opening_count = query.count("(")
    closing_count = query.count(")")
    while opening_count > closing_count:
        # Find last unclosed opening parenthesis position
        query, opening_count = remove_last_symbol_occurrence(
            query, opening_count, "("
        )
    while closing_count > opening_count:
        # Find last unclosed closing parenthesis position
        query, closing_count = remove_last_symbol_occurrence(
            query, closing_count, ")"
        )
    return query


def sanitize_unbalanced_quotes(query: str) -> str:
    """Sanitize a query by removing unbalanced quotes.

    :param query: The input query string
    :return: The sanitized query string, after removing unbalanced quotes.
    """
    quotes_count = query.count('"')
    while quotes_count % 2 != 0:
        query, quotes_count = remove_last_symbol_occurrence(
            query, quotes_count, '"'
        )
    return query

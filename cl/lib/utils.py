import re
from collections.abc import Iterable
from collections.abc import Iterable as IterableType
from itertools import chain, islice, tee
from re import Match
from typing import Any

from django.core.cache import cache

from cl.lib.courts import lookup_child_courts_cache
from cl.lib.model_helpers import clean_docket_number, is_docket_number
from cl.lib.types import CleanData
from cl.search.exception import DisallowedWildcardPattern, QueryType


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

    This is from: https://stackoverflow.com/a/1012089/64911

    This will allow you to lazily iterate a list such that as you iterate, you
    get a tuple containing the previous, current, and next value.
    """
    prevs, items, nexts = tee(some_iterable, 3)
    prevs = chain([None], prevs)
    nexts = chain(islice(nexts, 1, None), [None])
    return zip(prevs, items, nexts)


def is_iter(item: Any) -> bool:
    # See: https://stackoverflow.com/a/1952655/64911
    return isinstance(item, Iterable)


def remove_duplicate_dicts(dicts: list[dict]) -> list[dict]:
    """Given a list of dicts, remove any that are the same.

    See: https://stackoverflow.com/a/9427216/64911
    """
    return [dict(t) for t in {tuple(d.items()) for d in dicts}]


def human_sort(
    unordered_list: IterableType[str | tuple[str, Any]],
    key: str | None = None,
) -> IterableType[str | tuple[str, Any]]:
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


def get_child_court_ids_for_parents(selected_courts_string: str) -> str:
    """
    Retrieves and combines court IDs from both the given parents and their
    child courts and removing duplicates.

    :param selected_courts_string: The courts from the original user query.
    :return: A string containing the unique combination of parent and child courts.
    """
    unique_courts = set(re.findall(r'"(.*?)"', selected_courts_string))
    unique_courts.update(lookup_child_courts_cache(list(unique_courts)))
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


def check_query_for_disallowed_wildcards(query_string: str) -> bool:
    """Check if the query_string contains not allowed wildcards that can be
    really expensive.
    https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-wildcard

    * at the beginning of a term
    * in a term with less than 3 characters.
    ! in a term with less than 3 characters.

    Like:
    *ing
    a* or !a

    :param query_string: The query string to be checked.
    :return: A boolean indicating if the query string contains not allowed wildcards.
    """

    # Match any term that starts with *
    wildcard_start = r"(?:^|\s)\*\w+"

    # Match any term with less than 3 chars that ends with *
    wildcard_end = r"(?:^|\s)\w{1,2}\*(?=$|\s)"

    # Match any term with less than 3 chars that starts with !
    root_expander_short_term = r"(?:^|\s)\![^\s]{1,2}(?=$|\s)"

    if any(
        re.search(pattern, query_string)
        for pattern in [wildcard_start, wildcard_end, root_expander_short_term]
    ):
        return True
    return False


def perform_special_character_replacements(query_string: str) -> str:
    """Perform a series of special character replacements in the given query
    string to clean it up and support the % &, !, and * search connectors.

    :param query_string: The user query string.
    :return: The transformed query string with the specified replacements applied.
    """

    # Replace smart quotes with standard double quotes for consistency.
    query_string = re.sub(r"[“”]", '"', query_string)

    # Replace % (but not) by NOT
    query_string = re.sub(r" % ", " NOT ", query_string)

    # Replace & by AND
    query_string = re.sub(r" & ", " AND ", query_string)

    # Replace ! (root expander) at the beginning of words with * at the end.
    root_expander_pattern = r"(^|\s)!([a-zA-Z]+)"
    root_expander_replacement = r"\1\2*"
    query_string = re.sub(
        root_expander_pattern, root_expander_replacement, query_string
    )

    # Replace * (universal character) that is not at the end of a word with ?.
    universal_char_pattern = r"\*(?=\w)"
    universal_char_replacement = "?"
    query_string = re.sub(
        universal_char_pattern, universal_char_replacement, query_string
    )

    return query_string


def cleanup_main_query(query_string: str) -> str:
    """Enhance the query string with some simple fixes

     - Check for expensive wildcards and thrown an error if found.
     - Perform special character replacements for search connectors.
     - Make any numerical queries into phrases (except dates)
     - Add hyphens to district docket numbers that lack them
     - Ignore tokens inside phrases
     - Handle query punctuation correctly by mostly ignoring it
     - Removes spaces between phrase query and tilde(~) operator
     - Capture "court_id:court" queries, retrieve the child courts for each
     court in the query, append them, and then add them back to the original
     query.

    :param query_string: The query string from the form
    :return The enhanced query string
    """
    inside_a_phrase = False
    cleaned_items = []

    if check_query_for_disallowed_wildcards(query_string):
        raise DisallowedWildcardPattern(QueryType.QUERY_STRING)

    query_string = perform_special_character_replacements(query_string)

    # Tweaks to the following regex for special characters exceptions
    # like §, $, %, and ¶ should also be applied to type_table in
    # custom_word_delimiter_filter.
    for item in re.split(r'([^a-zA-Z0-9_\-^~":§$%¶]+)', query_string):
        if not item:
            continue

        if (
            item.startswith('"')
            or item.endswith('"')
            or bool(re.match(r'\w+:"[^"]', item))
        ):
            # Start or end of a phrase or a fielded query using quotes e.g: field:"test"
            # flip whether we're inside a phrase
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

        if "docketNumber:" in item:
            potential_docket_number = item.split("docketNumber:", 1)[1]

            if not potential_docket_number:
                # The docket_number is wrapped in parentheses
                cleaned_items.append(item)
            else:
                # Improve the docket_number query by:
                # If it's a known docket_number format, wrap it in quotes and
                # add a ~1 slop to match slight variations like 1:21-bk-1234-ABC → 1:21-bk-1234
                # If it's not a known docket_number format, just wrap it in
                # quotes to avoid syntax errors caused by : in the number.
                slop_suffix = (
                    "~1" if is_docket_number(potential_docket_number) else ""
                )
                cleaned_items.append(
                    f'docketNumber:"{potential_docket_number}"{slop_suffix}'
                )
            continue

        if any([not_numeric, is_date_str]):
            cleaned_items.append(item)
            continue

        m = re.match(r"(\d{2})(cv|cr|mj|po)(\d{1,5})", item)
        if m:
            # It's a docket number missing hyphens, e.g. 19cv38374
            item = "-".join(m.groups())

        # Some sort of number, probably a docket number or other type of number
        # Wrap in quotes to do a phrase search
        if is_docket_number(item):
            # Confirm is a docket number and clean it. So docket_numbers with
            # suffixes can be searched: 1:21-bk-1234-ABC -> 1:21-bk-1234,
            item = clean_docket_number(item)
            # Adds a proximity query of ~1 to match
            # numbers like 1:21-cv-1234 -> 21-1234
            cleaned_items.append(f'docketNumber:"{item}"~1')
        else:
            cleaned_items.append(f'"{item}"')

    cleaned_query = "".join(cleaned_items)
    # Removes spaces between phrase query and tilde(~) operator
    cleaned_query = re.sub(r'(")\s*(?=~\d+)', r"\1", cleaned_query)
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

    pattern = r"/s(?!\w)|/p(?!\w)"
    return bool(re.search(pattern, query))


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
    all_quotes = re.findall(r"[“”\"]", query)
    return len(all_quotes) % 2 != 0


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
    # Replace smart quotes with standard double quotes for consistency.
    query = re.sub(r"[“”]", '"', query)
    quotes_count = query.count('"')
    while quotes_count % 2 != 0:
        query, quotes_count = remove_last_symbol_occurrence(
            query, quotes_count, '"'
        )
    return query


def map_to_docket_entry_sorting(sort_string: str) -> str:
    """Convert a RECAP sorting param to a docket entry sorting parameter."""
    if sort_string == "dateFiled asc":
        return "entry_date_filed asc"
    elif sort_string == "dateFiled desc":
        return "entry_date_filed desc"
    else:
        return sort_string


def append_value_in_cache(key, value):
    """Append a value to a cached list associated with the given key.
    If the key does not exist, a new list is created and the value is added.

    :param key: The cache key to retrieve or store the list.
    :param value: The value to be appended to the cached list.
    :return: None.
    """

    cached_docs = cache.get(key)
    if cached_docs is None:
        cached_docs = []
    cached_docs.append(value)
    one_month = 60 * 60 * 24 * 7 * 4
    cache.set(key, cached_docs, timeout=one_month)

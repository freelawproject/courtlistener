"""
Template filters to partition lists into rows or columns.

A common use-case is for splitting a list into a table with columns::

    {% load partition %}
    <table>
    {% for row in mylist|columns:3 %}
        <tr>
        {% for item in row %}
            <td>{{ item }}</td>
        {% endfor %}
        </tr>
    {% endfor %}
    </table>
"""

from collections.abc import Iterable
from typing import TypeVar

from django.template import Library

register = Library()

T = TypeVar("T")


def rows(thelist: Iterable[T], n: int | str) -> list[list[T]]:
    """
    Break a list into ``n`` rows, filling up each row to the maximum equal
    length possible. For example::

        >>> l = range(10)

        >>> rows(l, 2)
        [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]

        >>> rows(l, 3)
        [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]

        >>> rows(l, 4)
        [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]

        >>> rows(l, 5)
        [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9]]

        >>> rows(l, 9)
        [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [], [], [], []]

        # This filter will always return `n` rows, even if some are empty:
        >>> rows(range(2), 3)
        [[0], [1], []]
    """
    try:
        n = int(n)
        items = list(thelist)
    except (ValueError, TypeError):
        return [list(thelist)]
    list_len = len(items)
    split = list_len // n

    if list_len % n != 0:
        split += 1
    return [items[split * i : split * (i + 1)] for i in range(n)]


def rows_distributed(thelist: Iterable[T], n: int | str) -> list[list[T]]:
    """
    Break a list into ``n`` rows, distributing columns as evenly as possible
    across the rows. For example::

        >>> l = range(10)

        >>> rows_distributed(l, 2)
        [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]

        >>> rows_distributed(l, 3)
        [[0, 1, 2, 3], [4, 5, 6], [7, 8, 9]]

        >>> rows_distributed(l, 4)
        [[0, 1, 2], [3, 4, 5], [6, 7], [8, 9]]

        >>> rows_distributed(l, 5)
        [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9]]

        >>> rows_distributed(l, 9)
        [[0, 1], [2], [3], [4], [5], [6], [7], [8], [9]]

        # This filter will always return `n` rows, even if some are empty:
        >>> rows(range(2), 3)
        [[0], [1], []]
    """
    try:
        n = int(n)
        items = list(thelist)
    except (ValueError, TypeError):
        return [list(thelist)]
    list_len = len(items)
    split = list_len // n

    remainder = list_len % n
    offset = 0
    result_rows: list[list[T]] = []
    for i in range(n):
        if remainder:
            start, end = (split + 1) * i, (split + 1) * (i + 1)
        else:
            start, end = split * i + offset, split * (i + 1) + offset
        result_rows.append(items[start:end])
        if remainder:
            remainder -= 1
            offset += 1
    return result_rows


def columns(thelist: Iterable[T], n: int | str) -> list[list[T]]:
    """
    Break a list into ``n`` columns, filling up each column to the maximum equal
    length possible. For example::

        >>> from pprint import pprint
        >>> for i in range(7, 11):
        ...     print '%sx%s:' % (i, 3)
        ...     pprint(columns(range(i), 3), width=20)
        7x3:
        [[0, 3, 6],
         [1, 4],
         [2, 5]]
        8x3:
        [[0, 3, 6],
         [1, 4, 7],
         [2, 5]]
        9x3:
        [[0, 3, 6],
         [1, 4, 7],
         [2, 5, 8]]
        10x3:
        [[0, 4, 8],
         [1, 5, 9],
         [2, 6],
         [3, 7]]

        # Note that this filter does not guarantee that `n` columns will be
        # present:
        >>> pprint(columns(range(4), 3), width=10)
        [[0, 2],
         [1, 3]]
    """
    try:
        n = int(n)
        items = list(thelist)
    except (ValueError, TypeError):
        return [list(thelist)]
    list_len = len(items)
    split = list_len // n
    if list_len % n != 0:
        split += 1
    return [items[i::split] for i in range(split)]


register.filter(rows)
register.filter(rows_distributed)
register.filter(columns)


def _test() -> None:
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()

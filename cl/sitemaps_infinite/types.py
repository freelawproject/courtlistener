from typing import TypedDict

"""
A TypedDict representing the data associated with large sitemaps pre-generation process.
It holds the place where the pre-generation task stopped so next task invocation can continue from there.

The keys in this TypedDict are:
- `section`: The section of the response that this cursor data applies to, as a string or bytes.
- `last_page`: The index of the last page in the section, as an integer or string.
- `has_next`: A boolean indicating whether there are more pages available after this one.
"""


class TaskCursorData(TypedDict):
    section: str | bytes
    last_page: int | str
    has_next: int


"""
A dictionary mapping sitemap section names to the number of pages in that section.

e.g. {"opinions": 1000, "dockets": 10000}
"""
SitemapsPagesNumber = dict[str, int]

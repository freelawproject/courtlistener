"""Page-order sequencing for a reporter volume's table of contents.

A reporter volume listing is most useful in the order the volume itself is
bound: first page to last. Getting there needs two things the database doesn't
store directly.

First, ordering. `Citation.page` is a TextField, so "10" sorts before "9"
lexically. Pages are parsed to integers here instead of in SQL because a
handful of citations carry non-numeric pages (roman numerals in front matter,
"Appx. 4", and so on) that would abort a database-side cast.

Second, extent. No column records where an opinion *ends*; a Citation marks
only where it begins. Extent therefore comes from one of two places, and
which one matters enormously:

- Measured, from star pagination inside the opinion's own text. These are the
  markers the printed reporter's page breaks left behind, and they are
  independent of the neighbouring cases.
- Inferred, from the page the following case begins on, when the text carries
  no markers. A case is then credited with the pages up to, but not
  including, the next case's first page.

Only the measured kind can reveal a coverage gap. Inferred spans are
contiguous by construction, so a case missing from the volume silently
inflates its predecessor's span rather than leaving a hole: the very thing
worth detecting is the thing inference cannot see. Where a measured extent
stops short of the next case, those pages are reported as a gap.

That evidence is uneven, and the caller should say so rather than imply a
volume is complete. Many older opinions carry no markers at all, and a
missing marker is not evidence of a missing page; such cases are left
unchecked instead of being flagged. Markers also have to be filtered to the
window the case could occupy, since a parallel citation can drag another
reporter's pagination into the text.

Finally, several cases often share a first page -- in early reporters a page
may hold four short notes -- and their individual extents are then
indeterminate. Such rows report a bound rather than a count, and a gap is
judged against the furthest-reaching case on the page, so a short case does
not raise a flag while a page-mate runs on past it.

Nothing here imports Django, so the sequencing can be tested on its own.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

# Leading digits of a page value; tolerates "4", "4a" and " 4 ".
_LEADING_DIGITS = re.compile(r"\s*(\d+)")

# Star pagination: the markers that record where the printed reporter broke
# to a new page. Harvard's XML tags them; Lawbox and Columbia text uses the
# older *N convention.
_PAGE_NUMBER_TAG = re.compile(r'<page-number[^>]*label="(\d+)"')
_STAR_PAGE = re.compile(r"(?<![\w*])\*(\d{1,5})\b")


class _HasVolumeReporterPage(Protocol):
    """The three Citation fields this module reads."""

    @property
    def volume(self) -> str: ...
    @property
    def reporter(self) -> str: ...
    @property
    def page(self) -> str: ...


class _CitationsManager(Protocol):
    """The related manager a cluster exposes its citations through."""

    def all(self) -> Iterable[_HasVolumeReporterPage]: ...


class _HasCitations(Protocol):
    """A cluster whose citations have been prefetched."""

    @property
    def citations(self) -> _CitationsManager: ...


def parse_page(page: str | int | None) -> int | None:
    """Read a citation's page as an integer, or None when it isn't numeric.

    :param page: The raw page value from a Citation.
    :return: The leading integer, or None for empty and non-numeric pages.
    """
    if page is None:
        return None
    if isinstance(page, int):
        return page
    match = _LEADING_DIGITS.match(page)
    return int(match.group(1)) if match else None


def parse_star_pages(text: str | None) -> list[int]:
    """Collect the page numbers star pagination records inside an opinion.

    These are the only in-database evidence of where an opinion *ends*. A
    Citation records only where it begins, so without these a case's extent
    can only be inferred from the next case, which can never reveal a case
    that is missing.

    :param text: Stored opinion text, in any of CourtListener's formats.
    :return: Every page number marked in the text, unfiltered and unsorted.
    """
    if not text:
        return []
    return [int(m) for m in _PAGE_NUMBER_TAG.findall(text)] + [
        int(m) for m in _STAR_PAGE.findall(text)
    ]


def last_marked_page(
    markers: Iterable[int], first_page: int, bound: int | None
) -> int | None:
    """Find the last page an opinion is shown to reach, or None if unmarked.

    Markers are filtered to the window the case could actually occupy.
    Anything before its own first page belongs to earlier matter, and
    anything past the following case's first page is another reporter's
    pagination bleeding in through a parallel citation -- which does happen,
    so it is discarded rather than trusted.

    :param markers: Page numbers found in the opinion text.
    :param first_page: The case's first page in this volume.
    :param bound: First page of the next case, or None if it is the last.
    :return: The highest credible marked page, or None when none qualify.
    """
    usable = [
        m for m in markers if m >= first_page and (bound is None or m <= bound)
    ]
    return max(usable) if usable else None


@dataclass
class VolumeSpan:
    """Where one case sits in its volume, and how much of it the case fills.

    page_count and last_page are None when the extent is unknown: for the last
    case in the volume (nothing follows it to bound it) and for cases whose
    page is non-numeric.

    When several cases begin on the same page, page_count describes the run of
    pages they occupy *together*, since there is no way to divide it between
    them. Read it as a per-case figure only when cases_on_page is 1, which is
    what length_label takes care of.
    """

    page: int | None
    # First page of the next case in the volume; bounds this case's extent.
    next_page: int | None
    last_page: int | None
    page_count: int | None
    # How many cases in the volume begin on this same page, this one included.
    cases_on_page: int
    # Last page the opinion's own text is shown to reach, from star
    # pagination. None when the text carries no usable marker, which is
    # not evidence of anything either way.
    text_last_page: int | None = None
    # The furthest any case beginning on this same page is shown to reach.
    # Gaps are judged against this rather than text_last_page: when cases
    # share a page, a short one proves nothing while a page-mate runs on.
    group_last_page: int | None = None

    @property
    def shares_first_page(self) -> bool:
        """Whether another case in the volume begins on this page too."""
        return self.cases_on_page > 1

    @property
    def gap_pages(self) -> int | None:
        """Count the pages between this case's end and the next case's start.

        This is the whole point of listing page numbers: a positive count
        means the volume printed pages that CourtListener holds no case for.
        None means the question can't be asked -- no end marker in the text,
        or nothing following this case to measure against.
        """
        reach = self.group_last_page or self.text_last_page
        if reach is None or self.next_page is None:
            return None
        # Ending on the page the next case starts on is normal, not a gap.
        missing = self.next_page - reach - 1
        return missing if missing > 0 else 0

    @property
    def has_gap(self) -> bool:
        """Whether pages are unaccounted for between this case and the next."""
        return bool(self.gap_pages)

    @property
    def text_page_count(self) -> int | None:
        """How many pages the opinion's text actually covers, if marked."""
        if self.page is None or self.text_last_page is None:
            return None
        return self.text_last_page - self.page + 1

    @property
    def display_last_page(self) -> int | None:
        """The last page to show for this case, measured where possible.

        Prefers the opinion's own text over the inferred bound, so the span
        shown and the length shown describe the same thing. For cases
        sharing a first page the inferred bound is kept, since their pages
        cannot be divided up at all.
        """
        if not self.shares_first_page and self.text_last_page is not None:
            return self.text_last_page
        return self.last_page

    @property
    def label(self) -> str:
        """Render the span the way a reporter's own table of contents would."""
        if self.page is None:
            return ""
        end = self.display_last_page
        if end is None:
            # Nothing bounds this case, so claim only its first page.
            return f"{self.page}–"
        if end <= self.page:
            return str(self.page)
        return f"{self.page}–{end}"

    @property
    def length_label(self) -> str:
        """State the case's length without claiming more than is known.

        A page shared between cases cannot be divided between them, so a
        shared row reports a bound rather than a count. Were each sharer to
        report the whole run instead, the lengths down the column would sum
        to more pages than the volume holds.

        Failing that, the opinion's own text is a better authority than the
        distance to the next case, since the distance silently absorbs any
        case missing in between. Where the two disagree, that difference is
        the gap, and gap_pages reports it.
        """
        if self.shares_first_page and self.page_count is not None:
            if self.page_count == 1:
                # Several cases inside one page: each is a fraction of it.
                return "<1"
            return f"≤{self.page_count}"
        if self.text_page_count is not None:
            return str(self.text_page_count)
        if self.page_count is None:
            return ""
        return str(self.page_count)

    @property
    def length_is_measured(self) -> bool:
        """Whether the length was measured, rather than inferred."""
        return not self.shares_first_page and self.text_page_count is not None


def citation_page_for(
    cluster: _HasCitations, reporter: str, volume: str
) -> int | None:
    """Find a cluster's first page within one specific reporter volume.

    A cluster usually carries parallel citations, so the page is only
    meaningful once the reporter and volume are pinned down.

    :param cluster: A cluster with prefetched citations.
    :param reporter: The reporter abbreviation being listed.
    :param volume: The volume being listed.
    :return: The first page in that volume, or None if there isn't one.
    """
    pages = [
        parsed
        for citation in cluster.citations.all()
        if citation.reporter == reporter
        and citation.volume == volume
        and (parsed := parse_page(citation.page)) is not None
    ]
    # A cluster can hold more than one citation to the same volume; the
    # earliest page is where the case starts.
    return min(pages) if pages else None


def sequence_volume[T: _HasCitations](
    clusters: list[T],
    reporter: str,
    volume: str,
    markers: Callable[[T], Iterable[int]] | None = None,
) -> list[tuple[T, VolumeSpan]]:
    """Order a volume's cases by page and work out how far each one runs.

    Ties are broken by the order the clusters arrive in, so the caller's
    secondary ordering (date filed, say) decides how cases sharing a first
    page are listed. Cases with no numeric page in this volume sort last,
    where they can be seen rather than silently dropped.

    :param clusters: The volume's clusters, with citations prefetched.
    :param reporter: The reporter abbreviation being listed.
    :param volume: The volume being listed.
    :param markers: Optional lookup returning the star-pagination pages found
        in a cluster's text. Supplying it is what makes gap detection
        possible; without it spans are still derived, but a missing case
        cannot be spotted.
    :return: (cluster, span) pairs in page order.
    """
    paged = [
        (cluster, citation_page_for(cluster, reporter, volume))
        for cluster in clusters
    ]
    # Stable, so clusters sharing a page keep the caller's ordering.
    paged.sort(key=lambda pair: (pair[1] is None, pair[1] or 0))

    first_pages = sorted({page for _, page in paged if page is not None})
    # Where each page's run ends: the next first page in the volume.
    next_first_page = dict(zip(first_pages, first_pages[1:], strict=False))
    cases_on_page: dict[int, int] = {}
    for _, page in paged:
        if page is not None:
            cases_on_page[page] = cases_on_page.get(page, 0) + 1

    sequenced = []
    for cluster, page in paged:
        next_page = next_first_page.get(page) if page is not None else None
        if page is None or next_page is None:
            last_page = None
            page_count = None
        else:
            # Credit the pages before the next case begins, so spans never
            # overlap. See the module docstring on the shared-page case.
            last_page = next_page - 1
            page_count = next_page - page
        text_last_page = None
        if markers is not None and page is not None:
            text_last_page = last_marked_page(
                markers(cluster), page, next_page
            )
        sequenced.append(
            (
                cluster,
                VolumeSpan(
                    page=page,
                    next_page=next_page,
                    last_page=last_page,
                    page_count=page_count,
                    cases_on_page=(
                        cases_on_page.get(page, 1) if page is not None else 1
                    ),
                    text_last_page=text_last_page,
                ),
            )
        )

    # How far the cases on each page collectively reach. Judging a gap by a
    # single case would flag one that ends early while a page-mate runs on.
    group_reach: dict[int, int] = {}
    for _, span in sequenced:
        if span.page is None or span.text_last_page is None:
            continue
        current = group_reach.get(span.page)
        if current is None or span.text_last_page > current:
            group_reach[span.page] = span.text_last_page
    for _, span in sequenced:
        if span.page is not None:
            span.group_last_page = group_reach.get(span.page)

    return sequenced


@dataclass
class VolumeSummary:
    """Volume-level totals for the heading above the table of contents."""

    case_count: int
    first_page: int | None
    last_page: int | None
    # Cases that begin on a page another case also begins on.
    shared_page_cases: int
    # Cases with no numeric page in this volume.
    unpaged_cases: int
    # Places where the volume printed pages no case here accounts for.
    gap_count: int = 0
    gap_pages: int = 0
    # Cases whose text carries no end marker, so they could not be checked.
    unchecked_cases: int = 0

    @property
    def page_extent(self) -> int | None:
        """How many pages the listed cases span, first to last."""
        if self.first_page is None or self.last_page is None:
            return None
        return self.last_page - self.first_page + 1

    @property
    def checked_cases(self) -> int:
        """How many cases could actually be checked for a following gap."""
        return self.case_count - self.unchecked_cases


def summarize_volume[T: _HasCitations](
    sequenced: list[tuple[T, VolumeSpan]],
) -> VolumeSummary:
    """Total up a sequenced volume for display above the listing.

    :param sequenced: The output of sequence_volume().
    :return: The volume's totals.
    """
    pages = [span.page for _, span in sequenced if span.page is not None]
    spans = [span for _, span in sequenced]
    gaps_by_page = {
        s.page: s.gap_pages
        for s in spans
        if s.page is not None and s.gap_pages
    }
    return VolumeSummary(
        case_count=len(sequenced),
        first_page=min(pages) if pages else None,
        last_page=max(pages) if pages else None,
        shared_page_cases=sum(1 for s in spans if s.shares_first_page),
        unpaged_cases=sum(1 for s in spans if s.page is None),
        # A gap follows a page, not a row, so cases sharing a flagged page
        # describe one gap between them rather than one apiece.
        gap_count=len(gaps_by_page),
        gap_pages=sum(gaps_by_page.values()),
        # The last case has nothing after it, so it is not checkable either.
        unchecked_cases=sum(1 for s in spans if s.gap_pages is None),
    )

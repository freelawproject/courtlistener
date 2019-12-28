#!/usr/bin/env python
# encoding: utf-8
import re
import sys

from django.utils.timezone import now
from juriscraper.lib.html_utils import get_visible_text
from reporters_db import EDITIONS, REPORTERS, VARIATIONS_ONLY

from cl.citations import reporter_tokenizer
from cl.lib.roman import isroman
from cl.search.models import Court
from cl.citations.models import (
    FullCitation,
    IdCitation,
    SupraCitation,
    ShortformCitation,
)


FORWARD_SEEK = 20

BACKWARD_SEEK = 28  # Median case name length in the db is 28 (2016-02-26)

STOP_TOKENS = [
    "v",
    "re",
    "parte",
    "denied",
    "citing",
    "aff'd",
    "affirmed",
    "remanded",
    "see",
    "granted",
    "dismissed",
]

# Store court values to avoid repeated DB queries
if not set(sys.argv).isdisjoint(["test", "syncdb", "shell", "migrate"]) or any(
    "pytest" in s for s in set(sys.argv)
):
    # If it's a test, we can't count on the database being prepped, so we have
    # to load lazily
    ALL_COURTS = Court.objects.all().values("citation_string", "pk")
else:
    # list() forces early evaluation of the queryset so we don't have issues
    # with closed cursors.
    ALL_COURTS = list(Court.objects.all().values("citation_string", "pk"))


# Adapted from nltk Penn Treebank tokenizer
def strip_punct(text):
    # starting quotes
    text = re.sub(r"^[\"\']", r"", text)
    text = re.sub(r"(``)", r"", text)
    text = re.sub(r'([ (\[{<])"', r"", text)

    # punctuation
    text = re.sub(r"\.\.\.", r"", text)
    text = re.sub(r"[,;:@#$%&]", r"", text)
    text = re.sub(r'([^\.])(\.)([\]\)}>"\']*)\s*$', r"\1", text)
    text = re.sub(r"[?!]", r"", text)

    text = re.sub(r"([^'])' ", r"", text)

    # parens, brackets, etc.
    text = re.sub(r"[\]\[\(\)\{\}\<\>]", r"", text)
    text = re.sub(r"--", r"", text)

    # ending quotes
    text = re.sub(r'"', "", text)
    text = re.sub(r"(\S)(\'\'?)", r"\1", text)

    return text.strip()


def is_scotus_reporter(citation):
    try:
        reporter = REPORTERS[citation.canonical_reporter][
            citation.lookup_index
        ]
    except (TypeError, KeyError):
        # Occurs when citation.lookup_index is None
        return False

    if reporter:
        truisms = [
            (
                reporter["cite_type"] == "federal"
                and "supreme" in reporter["name"].lower()
            ),
            "scotus" in reporter["cite_type"].lower(),
        ]
        if any(truisms):
            return True
    else:
        return False


def is_neutral_tc_reporter(reporter):
    """Test whether the reporter is a neutral Tax Court reporter.

    These take the format of T.C. Memo YEAR-SERIAL

    :param reporter: A string of the reporter, e.g. "F.2d" or "T.C. Memo"
    :return True if a T.C. neutral citation, else False
    """
    if re.match(r"T\. ?C\. (Summary|Memo)", reporter):
        return True
    return False


def get_court_by_paren(paren_string, citation):
    """Takes the citation string, usually something like "2d Cir", and maps
    that back to the court code.

    Does not work on SCOTUS, since that court lacks parentheticals, and
    needs to be handled after disambiguation has been completed.
    """
    if citation.year is None:
        court_str = strip_punct(paren_string)
    else:
        year_index = paren_string.find(str(citation.year))
        court_str = strip_punct(paren_string[:year_index])

    court_code = None
    if court_str == u"":
        court_code = None
    else:
        # Map the string to a court, if possible.
        for court in ALL_COURTS:
            # Use startswith because citations are often missing final period,
            # e.g. "2d Cir"
            if court["citation_string"].startswith(court_str):
                court_code = court["pk"]
                break

    return court_code


def get_year(token):
    """Given a string token, look for a valid 4-digit number at the start and
    return its value.
    """
    token = strip_punct(token)
    if not token.isdigit():
        # Sometimes funny stuff happens?
        token = re.sub(r"(\d{4}).*", r"\1", token)
        if not token.isdigit():
            return None
    if len(token) != 4:
        return None
    year = int(token)
    if year < 1754:  # Earliest case in the database
        return None
    return year


def add_post_citation(citation, words):
    """Add to a citation object any additional information found after the base
    citation, including court, year, and possibly page range.

    Examples:
        Full citation: 123 U.S. 345 (1894)
        Post-citation info: year=1894

        Full citation: 123 F.2d 345, 347-348 (4th Cir. 1990)
        Post-citation info: year=1990, court="4th Cir.",
        extra (page range)="347-348"
    """
    # Start looking 2 tokens after the reporter (1 after page), and go to
    # either the end of the words list or to FORWARD_SEEK tokens from where you
    # started.
    fwd_sk = citation.reporter_index + FORWARD_SEEK
    for start in xrange(citation.reporter_index + 2, min(fwd_sk, len(words))):
        if words[start].startswith("("):
            # Get the year by looking for a token that ends in a paren.
            for end in xrange(start, start + FORWARD_SEEK):
                try:
                    has_ending_paren = words[end].find(")") > -1
                except IndexError:
                    # Happens with words like "(1982"
                    break
                if has_ending_paren:
                    # Sometimes the paren gets split from the preceding content
                    if words[end].startswith(")"):
                        citation.year = get_year(words[end - 1])
                    else:
                        citation.year = get_year(words[end])
                    citation.court = get_court_by_paren(
                        u" ".join(words[start : end + 1]), citation
                    )
                    break

            if start > citation.reporter_index + 2:
                # Then there's content between page and (), starting with a
                # comma, which we skip
                citation.extra = u" ".join(
                    words[citation.reporter_index + 2 : start]
                )
            break


def add_defendant(citation, words):
    """Scan backwards from 2 tokens before reporter until you find v., in re,
    etc. If no known stop-token is found, no defendant name is stored.  In the
    future, this could be improved.
    """
    start_index = None
    back_seek = citation.reporter_index - BACKWARD_SEEK
    for index in xrange(citation.reporter_index - 1, max(back_seek, 0), -1):
        word = words[index]
        if word == ",":
            # Skip it
            continue
        if strip_punct(word).lower() in STOP_TOKENS:
            if word == "v.":
                citation.plaintiff = words[index - 1]
            start_index = index + 1
            break
        if word.endswith(";"):
            # String citation
            break
    if start_index:
        citation.defendant = u" ".join(
            words[start_index : citation.reporter_index - 1]
        )


def extract_base_citation(words, reporter_index):
    """Construct and return a citation object from a list of "words"

    Given a list of words and the index of a federal reporter, look before and
    after for volume and page.  If found, construct and return a
    Citation object.

    If we are given neutral, tax court opinions we treat them differently.
    The formats often follow {REPORTER} {YEAR}-{ITERATIVE_NUMBER}
    ex. T.C. Memo. 2019-13
    """
    reporter = words[reporter_index]
    neutral_tc_reporter = is_neutral_tc_reporter(reporter)
    if neutral_tc_reporter:
        volume, page = (
            words[reporter_index + 1]
            .encode("utf-8")
            .replace("–", "-")
            .split("-")
        )
    else:
        # "Normal" reporter: XX F.2d YY
        if reporter_index == 0:
            return None
        volume = strip_punct(words[reporter_index - 1])
        page = strip_punct(words[reporter_index + 1])

    # Normalize volume and page
    if volume.isdigit():
        volume = int(volume)
    else:
        # No volume, therefore not a valid citation
        return None

    if page.isdigit():
        # Most page numbers will be digits.
        page = int(page)
    else:
        if isroman(page):
            # Some places like Nebraska have Roman numerals, e.g. in
            # '250 Neb. xxiv (1996)'. No processing needed.
            pass
        elif re.match(r"\d{1,6}[-]?[a-zA-Z]{1,6}", page):
            # Some places, like Connecticut, have pages like "13301-M".
            # Other places, like Illinois have "pages" like "110311-B".
            pass
        else:
            # Not Roman, and not a weird connecticut page number. Thus a bad
            # value. Abort.
            return None

    return Citation(
        reporter,
        page,
        volume,
        reporter_found=reporter,
        reporter_index=reporter_index,
    )


def is_date_in_reporter(editions, year):
    """Checks whether a year falls within the range of 1 to n editions of a
    reporter

    Editions will look something like:
        'editions': {'S.E.': {'start': datetime.datetime(1887, 1, 1),
                              'end': datetime.datetime(1939, 12, 31)},
                     'S.E.2d': {'start': datetime.datetime(1939, 1, 1),
                                'end': None}},
    """
    for date_dict in editions.values():
        if date_dict["end"] is None:
            date_dict["end"] = now()
        if date_dict["start"].year <= year <= date_dict["end"].year:
            return True
    return False


def disambiguate_reporters(citations):
    """Convert a list of citations to a list of unambiguous ones.

    Goal is to figure out:
     - citation.canonical_reporter
     - citation.lookup_index

    And there are a few things that can be ambiguous:
     - More than one variation.
     - More than one reporter for the key.
     - Could be an edition (or not)
     - All combinations of the above:
        - More than one variation.
        - More than one variation, with more than one reporter for the key.
        - More than one variation, with more than one reporter for the key,
          which is an edition.
        - More than one variation, which is an edition
        - ...

    For variants, we just need to sort out the canonical_reporter.

    If it's not possible to disambiguate the reporter, we simply have to drop
    it.
    """
    unambiguous_citations = []
    for citation in citations:
        # Non-variant items (P.R.R., A.2d, Wash., etc.)
        if REPORTERS.get(EDITIONS.get(citation.reporter)) is not None:
            citation.canonical_reporter = EDITIONS[citation.reporter]
            if len(REPORTERS[EDITIONS[citation.reporter]]) == 1:
                # Single reporter, easy-peasy.
                citation.lookup_index = 0
                unambiguous_citations.append(citation)
                continue
            else:
                # Multiple books under this key, but which is correct?
                if citation.year:
                    # attempt resolution by date
                    possible_citations = []
                    rep_len = len(REPORTERS[EDITIONS[citation.reporter]])
                    for i in range(0, rep_len):
                        if is_date_in_reporter(
                            REPORTERS[EDITIONS[citation.reporter]][i][
                                "editions"
                            ],
                            citation.year,
                        ):
                            possible_citations.append((citation.reporter, i,))
                    if len(possible_citations) == 1:
                        # We were able to identify only one hit
                        # after filtering by year.
                        citation.reporter = possible_citations[0][0]
                        citation.lookup_index = possible_citations[0][1]
                        unambiguous_citations.append(citation)
                        continue

        # Try doing a variation of an edition.
        elif VARIATIONS_ONLY.get(citation.reporter) is not None:
            if len(VARIATIONS_ONLY[citation.reporter]) == 1:
                # Only one variation -- great, use it.
                citation.canonical_reporter = EDITIONS[
                    VARIATIONS_ONLY[citation.reporter][0]
                ]
                cached_variation = citation.reporter
                citation.reporter = VARIATIONS_ONLY[citation.reporter][0]
                if len(REPORTERS[citation.canonical_reporter]) == 1:
                    # It's a single reporter under a misspelled key.
                    citation.lookup_index = 0
                    unambiguous_citations.append(citation)
                    continue
                else:
                    # Multiple reporters under a single misspelled key
                    # (e.g. Wn.2d --> Wash --> Va Reports, Wash or
                    #                          Washington Reports).
                    if citation.year:
                        # attempt resolution by date
                        possible_citations = []
                        rep_can = len(REPORTERS[citation.canonical_reporter])
                        for i in range(0, rep_can):
                            if is_date_in_reporter(
                                REPORTERS[citation.canonical_reporter][i][
                                    "editions"
                                ],
                                citation.year,
                            ):
                                possible_citations.append(
                                    (citation.reporter, i)
                                )
                        if len(possible_citations) == 1:
                            # We were able to identify only one hit after
                            # filtering by year.
                            citation.lookup_index = possible_citations[0][1]
                            unambiguous_citations.append(citation)
                            continue
                    # Attempt resolution by unique variation
                    # (e.g. Cr. can only be Cranch[0])
                    possible_citations = []
                    reps = REPORTERS[citation.canonical_reporter]
                    for i in range(0, len(reps)):
                        for variation in REPORTERS[
                            citation.canonical_reporter
                        ][i]["variations"].items():
                            if variation[0] == cached_variation:
                                possible_citations.append((variation[1], i))
                    if len(possible_citations) == 1:
                        # We were able to find a single match after filtering
                        # by variation.
                        citation.lookup_index = possible_citations[0][1]
                        unambiguous_citations.append(citation)
                        continue
            else:
                # Multiple variations, deal with them.
                possible_citations = []
                for reporter_key in VARIATIONS_ONLY[citation.reporter]:
                    for i in range(0, len(REPORTERS[EDITIONS[reporter_key]])):
                        # This inner loop works regardless of the number of
                        # reporters under the key.
                        key = REPORTERS[EDITIONS[reporter_key]]
                        cite_year = citation.year
                        if is_date_in_reporter(key[i]["editions"], cite_year):
                            possible_citations.append((reporter_key, i,))
                if len(possible_citations) == 1:
                    # We were able to identify only one hit after filtering by
                    # year.
                    citation.canonical_reporter = EDITIONS[
                        possible_citations[0][0]
                    ]
                    citation.reporter = possible_citations[0][0]
                    citation.lookup_index = possible_citations[0][1]
                    unambiguous_citations.append(citation)
                    continue

    return unambiguous_citations


def get_citations(
    text,
    html=True,
    do_post_citation=True,
    do_defendant=True,
    disambiguate=True,
):
    if html:
        text = get_visible_text(text)
    words = reporter_tokenizer.tokenize(text)
    citations = []
    # Exclude first and last tokens when looking for reporters, because valid
    # citations must have a volume before and a page after the reporter.
    for i in xrange(0, len(words) - 1):
        # Find reporter
        if words[i] in (EDITIONS.keys() + VARIATIONS_ONLY.keys()):
            citation = extract_base_citation(words, i)
            if citation is None:
                # Not a valid citation; continue looking
                continue
            if do_post_citation:
                add_post_citation(citation, words)
            if do_defendant:
                add_defendant(citation, words)
            citations.append(citation)

    if disambiguate:
        # Disambiguate or drop all the reporters
        citations = disambiguate_reporters(citations)

    for citation in citations:
        if not citation.court and is_scotus_reporter(citation):
            citation.court = "scotus"

    return citations

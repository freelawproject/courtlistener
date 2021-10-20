import html
import operator
import re
from datetime import date
from functools import reduce
from typing import List, Optional, Union

from dateutil.relativedelta import relativedelta
from django.db.models import Q, QuerySet
from django.utils.html import strip_tags
from nameparser import HumanName

from cl.people_db.models import SUFFIX_LOOKUP, Person

# list of words that aren't judge names
NOT_JUDGE_WORDS = [
    "above",
    "absent",
    "acting",
    "active",
    "adopted",
    "affirm",
    "after",
    "agrees",
    "all",
    "although",
    "and",
    "affirmed",
    "appeals",
    "appellate",
    "argument",
    "argued",
    "arj",
    "ass",
    "assign",
    "assigned",
    "assignment",
    "associate",
    "assistant",
    "attorney",
    "authorized",
    "available",
    "banc",
    "bankruptcy",
    "before",
    "board",
    "bold",
    "briefs",
    "but",
    "capacity",
    "case",
    "cause",
    "center",
    "certified",
    "chancellor",
    "ch",
    "chairman",
    "chief",
    "circuit",
    "columbia",
    "commission",
    "commissioner",
    "composed",
    "concur",
    "concurred",
    "concurrence",
    "concurring",
    "concurs",
    "conference",
    "conferences",
    "considered",
    "consisted",
    "consists",
    "constituting",
    "consultation",
    "continue",
    "court",
    "curiam",
    "decided",
    "decision",
    "delivered",
    "denial",
    "denials",
    "designation",
    "did",
    "died",
    "disqualified",
    "dissent",
    "dissented",
    "dissenting",
    "dissents",
    "district",
    "division",
    "editor",
    "emeritus",
    "even",
    "facts",
    "fellows",
    "final",
    "filed",
    "following",
    "footnote",
    "for",
    "full",
    "foregoing",
    "four",
    "further",
    "general",
    "his",
    "heard",
    "indiana",
    "indicated",
    "initial",
    "industrial",
    "issuance",
    "issuing",
    "italic",
    "joined",
    "joins",
    "judge",
    "judgement",
    "judges",
    "judgment",
    "judicial",
    "justice",
    "justices",
    "join",
    "jus",
    "magistrate",
    "majority",
    "making",
    "maryland",
    "may",
    "member",
    "memorandum",
    "not",
    "note",
    "number",
    "october",
    "of",
    "one",
    "opinion",
    "oral",
    "order",
    "page",
    "pair",
    "panel",
    "part",
    "participate",
    "participated",
    "participating",
    "participation",
    "petition",
    "per",
    "post",
    "prepared",
    "preparation",
    "present",
    "president",
    "presiding",
    "prior",
    "pro",
    "qualified",
    "recusal",
    "recuse",
    "recused",
    "reference",
    "rehearing",
    "report",
    "reported",
    "resigned",
    "reassignment",
    "resident",
    "resul",
    "result",
    "retired",
    "reverse",
    "reversed",
    "reservation",
    "sat",
    "section",
    "senior",
    "separate",
    "sit",
    "sitting",
    "special",
    "specially",
    "separately",
    "statement",
    "states",
    "stating",
    "submitted",
    "surrogate",
    "superior",
    "supernumerary",
    "taking",
    "tem",
    "term",
    "territorial",
    "texas",
    "the",
    "this",
    "though",
    "three",
    "time",
    "transfer",
    "two",
    "unanimous",
    "unpublished",
    "underline",
    "united",
    "vacancy",
    "vice",
    "votes",
    "warden",
    "was",
    "which",
    "while",
    "with",
    "without",
    "written",
    "january",
    "february",
    "march",
    "april",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]

# judge names can only be this size or larger
NAME_CUTOFF = 3

# for judges with small names, need an override
IS_JUDGE = {"wu", "re", "du", "de"}


def extract_judge_last_name(text: str) -> List[str]:
    """Find judge last names in a string of text.

    :param text: The text you wish to extract names from.
    :return: last names of judges in `text`.
    """
    text = text.lower() or ""
    # just use the first nonempty line (there's
    # sometimes a useless second line)
    line = text
    if "\n" in text:
        line = ""
        for l in text.split("\n"):
            if l:
                line = l
            break

    # Strip HTML elements and unescape HTML entities.
    line = strip_tags(line)
    line = html.unescape(line)

    # normalize text and get candidate judge names
    line = "".join([c if c.isalpha() else " " for c in line.lower()])
    names = []
    for word in line.split():
        word_too_short = len(word) < NAME_CUTOFF
        word_not_short_name = word not in IS_JUDGE
        if word_too_short and word_not_short_name:
            continue
        if word in NOT_JUDGE_WORDS:
            continue
        names.append(word)

    # identify which names are first and last names
    if len(names) == 0:
        return []
    elif len(names) == 1:
        return names
    else:
        last_names = [names[0]]
        for i in range(len(names))[1:]:
            first_last = f"{names[i - 1]} {names[i]}"
            first_m_last = r"%s [a-z]\.? %s" % (names[i - 1], names[i])
            if re.search(f"{first_last}|{first_m_last}", text):
                last_names[-1] = names[i]
                continue
            last_names.append(names[i])
    return last_names


def lookup_judge_by_full_name(
    name: Union[HumanName, str],
    court_id: str,
    event_date: Optional[date] = None,
) -> Optional[Person]:
    """Uniquely identifies a judge by both name and metadata.

    :param name: The judge's name, either as a str of the full name or as
    a HumanName object. Do NOT provide just the last name of the judge. If you
    do, it will be considered the judge's first name. You MUST provide their
    full name or a HumanName object. To look up a judge by last name, see the
    look_up_judge_by_last_name function. The str parsing used here is the
    heuristic approach used by nameparser.HumanName.
    :param court_id: The court where the judge did something
    :param event_date: The date when the judge did something
    :return Either the judge that matched the name in the court at the right
    time, or None.
    """
    if isinstance(name, str):
        name = HumanName(name)

    # check based on last name and court first
    filter_sets = [
        [Q(name_last__iexact=name.last), Q(positions__court_id=court_id)],
    ]
    # Then narrow by date
    if event_date is not None:
        filter_sets.append(
            [
                Q(
                    positions__date_start__lt=event_date
                    + relativedelta(years=1)
                )
                | Q(positions__date_start=None),
                Q(
                    positions__date_termination__gt=event_date
                    - relativedelta(years=1)
                )
                | Q(positions__date_termination=None),
            ]
        )

    # Then by first name
    if name.first:
        filter_sets.append([Q(name_first__iexact=name.first)])

    # Do middle name or initial next.
    if name.middle:
        initial = len(name.middle.strip(".,")) == 1
        if initial:
            filter_sets.append(
                [Q(name_middle__istartswith=name.middle.strip(".,"))]
            )
        else:
            filter_sets.append([Q(name_middle__iexact=name.middle)])

    # And finally, by suffix
    if name.suffix:
        suffix = SUFFIX_LOOKUP.get(name.suffix.lower())
        if suffix:
            filter_sets.append([Q(name_suffix__iexact=suffix)])

    # Query people DB, slowly adding more filters to the query. If we get zero
    # results, no luck. If we get one, great. If we get more than one, continue
    # filtering. If we expend all our filters and still have more than one,
    # just return None.
    applied_filters = []
    for filter_set in filter_sets:
        applied_filters.extend(filter_set)
        candidates = Person.objects.filter(*applied_filters)
        if len(candidates) == 0:
            # No luck finding somebody. Abort.
            return None
        elif len(candidates) == 1:
            # Got somebody unique!
            return candidates.first()
    return None


def lookup_judge_by_full_name_and_set_attr(
    item: object,
    target_field: str,
    full_name: str,
    court_id: str,
    event_date: date,
) -> None:
    """Lookup a judge by the attribute of an object

    :param item: The object containing the attribute you want to look up
    :param target_field: The field on the attribute you want to look up.
    :param full_name: The full name of the judge to look up.
    :param court_id: The court where the judge did something.
    :param event_date: The date the judge did something.
    :return None
    """
    if not full_name:
        return None
    judge = lookup_judge_by_full_name(full_name, court_id, event_date)
    if judge is not None:
        setattr(item, target_field, judge)


def lookup_judge_by_last_name(
    last_name: str,
    court_id: str,
    event_date: Optional[date] = None,
) -> Optional[Person]:
    """Look up the judge using their last name, a date and court"""
    hn = HumanName()
    hn.last = last_name
    return lookup_judge_by_full_name(hn, court_id, event_date)


def lookup_judges_by_last_name_list(
    last_names: List[str],
    court_id: str,
    event_date: Optional[date] = None,
) -> List[Person]:
    """Look up a group of judges by list of last names, a date, and a court"""
    found_people = []
    for last_name in last_names:
        hn = HumanName()
        hn.last = last_name
        person = lookup_judge_by_full_name(hn, court_id, event_date)
        if person is not None:
            found_people.append(person)
    return found_people


def lookup_judges_by_messy_str(
    s: str,
    court_id: str,
    event_date: Optional[date] = None,
) -> List[Person]:
    """Look up a group of judges by a messy string that might contain their
    names. (This is the least accurate way to look up judges.)
    """
    last_names = extract_judge_last_name(s)
    return lookup_judges_by_last_name_list(last_names, court_id, event_date)


def lookup_judge_by_first_or_last_name(queryset: QuerySet, s: str) -> QuerySet:
    """Find judge by first or last name

    :param queryset: Queryset to filter
    :param s: Query string to parse
    :return: Filter Queryset
    """
    # Possible DOS attack. Don't hit the DB.
    query_parts = [str.lower() for str in s.split()][:7]
    search_args = []
    for term in query_parts:
        for query in (
            "name_first__istartswith",
            "name_last__istartswith",
            "name_middle__istartswith",
            "name_suffix__istartswith",
        ):
            search_args.append(Q(**{query: term}))
    return queryset.filter(reduce(operator.or_, search_args))

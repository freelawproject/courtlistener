import html
import operator
import re
from datetime import date, timedelta
from functools import reduce
from typing import List, Optional, Set, Union

from dateutil.relativedelta import relativedelta
from django.db.models import Q, QuerySet
from django.utils.html import strip_tags
from nameparser import HumanName

from cl.people_db.models import SUFFIX_LOOKUP, Person

# list of words that aren't judge names
NOT_JUDGE_WORDS = [
    "abandoned",
    "abandonment",
    "about",
    "above",
    "absence",
    "absent",
    "absolutely",
    "abstained",
    "accelerating",
    "accept",
    "acceptance",
    "acceptation",
    "accepted",
    "accepting",
    "accident",
    "according",
    "accordingly",
    "accounting",
    "accurately",
    "accused",
    "acknowledged",
    "acquisition",
    "act",
    "acting",
    "active",
    "activities",
    "activity",
    "acts",
    "actual",
    "actually",
    "addendum",
    "addict",
    "addition",
    "additional",
    "additionally",
    "addressing",
    "adhere",
    "adhering",
    "adjudge",
    "adjudged",
    "adjudication",
    "adjusts",
    "administer",
    "administration",
    "administrative",
    "administrator",
    "admissible",
    "admission",
    "admits",
    "admitted",
    "admonishment",
    "adopt",
    "adopted",
    "advanced",
    "advise",
    "advised",
    "advisement",
    "affecting",
    "affirm",
    "affirmance",
    "affirmative",
    "affirmed",
    "affirming",
    "after",
    "again",
    "against",
    "age",
    "agent",
    "agreed",
    "agreement",
    "agreements",
    "agrees",
    "agricultural",
    "alienation",
    "all",
    "allowance",
    "allowed",
    "allowing",
    "almost",
    "alone",
    "also",
    "alter",
    "alternate",
    "alternative",
    "although",
    "ambiguity",
    "amended",
    "amending",
    "amendment",
    "among",
    "amount",
    "amounted",
    "amounting",
    "and",
    "annotatedannounced",
    "announcement",
    "announcing",
    "annually",
    "another",
    "any",
    "apart",
    "appeal",
    "appealability",
    "appealed",
    "appeals",
    "appearance",
    "appeared",
    "appearing",
    "appears",
    "appellant",
    "appellate",
    "appellee",
    "applicability",
    "applicable",
    "application",
    "applications",
    "applied",
    "apply",
    "applying",
    "appointed",
    "appointment",
    "appropriated",
    "approval",
    "approved",
    "april",
    "arbitration",
    "area",
    "argned",
    "argued",
    "argument",
    "arizona",
    "arj",
    "arkansas",
    "arrived",
    "article",
    "aside",
    "asked",
    "asociado",
    "asociados",
    "ass",
    "assented",
    "assessed",
    "assessment",
    "assessments",
    "assign",
    "assigned",
    "assignment",
    "assignments",
    "assistant",
    "associate",
    "associates",
    "association",
    "attached",
    "attachment",
    "attained",
    "attempt",
    "attempting",
    "attention",
    "attorney",
    "attorneys",
    "auditor",
    "august",
    "author",
    "authority",
    "authorization",
    "authorize",
    "authorized",
    "authorizes",
    "authorizing",
    "available",
    "awarded",
    "away",
    "back",
    "balance",
    "banc",
    "bankruptcy",
    "based",
    "because",
    "been",
    "before",
    "behalf",
    "behavior",
    "being",
    "believe",
    "believes",
    "belonged",
    "belonging",
    "below",
    "besides",
    "between",
    "big",
    "board",
    "bold",
    "boring",
    "both",
    "briefing",
    "briefs",
    "but",
    "cancelled",
    "cannot",
    "capacity",
    "case",
    "cases",
    "caso",
    "cause",
    "caused",
    "ceased",
    "center",
    "certified",
    "ch",
    "chairman",
    "chancellor",
    "changing",
    "chapter",
    "character",
    "charging",
    "chief",
    "circuit",
    "circumstances",
    "cited",
    "city",
    "claims",
    "close",
    "closed",
    "coincided",
    "columbia",
    "comment",
    "commerce",
    "commisioners",
    "commission",
    "commissioner",
    "committed",
    "company",
    "comparative",
    "compensation",
    "complained",
    "complaint",
    "composed",
    "compromised",
    "concealing",
    "concerning",
    "concerring",
    "concluding",
    "conclusion",
    "concur",
    "concurred",
    "concurrence",
    "concurrentes",
    "concurrently",
    "concurring",
    "concurs",
    "conducted",
    "conducting",
    "conference",
    "conferences",
    "conferring",
    "confessed",
    "confirmed",
    "connected",
    "consent",
    "consider",
    "consideration",
    "considered",
    "consist",
    "consisted",
    "consistent",
    "consisting",
    "consists",
    "consolidated",
    "constable",
    "constitute",
    "constituting",
    "constitution",
    "consultation",
    "contained",
    "continue",
    "contract",
    "contrary",
    "control",
    "convened",
    "conversion",
    "convicting",
    "conviction",
    "corporation",
    "corporations",
    "court",
    "credit",
    "curiam",
    "customs",
    "dated",
    "day",
    "deceased",
    "decedent",
    "december",
    "decided",
    "deciding",
    "decision",
    "declaring",
    "declined",
    "declining",
    "defendant",
    "deliberations",
    "delivered",
    "delivering",
    "denial",
    "denials",
    "denied",
    "deny",
    "describing",
    "deserving",
    "designated",
    "designation",
    "desiring",
    "destination",
    "determination",
    "determined",
    "did",
    "died",
    "directed",
    "directly",
    "disciplinary",
    "disclosed",
    "discrimination",
    "discussed",
    "discussing",
    "dismiss",
    "dismissal",
    "dismissed",
    "disposed",
    "disposition",
    "disqualified",
    "dissent",
    "dissented",
    "dissenting",
    "dissents",
    "district",
    "division",
    "dorchester",
    "doubted",
    "during",
    "each",
    "early",
    "earned",
    "editor",
    "eighth",
    "elected",
    "embraced",
    "emeritus",
    "eminently",
    "enforcement",
    "engaged",
    "entered",
    "entirely",
    "entitled",
    "entry",
    "eoncurring",
    "equally",
    "error",
    "espoused",
    "even",
    "ever",
    "except",
    "excepting",
    "exclusively",
    "excused",
    "exercised",
    "exist",
    "existing",
    "explained",
    "expressed",
    "expressing",
    "facts",
    "failed",
    "february",
    "fellows",
    "few",
    "filed",
    "final",
    "first",
    "five",
    "following",
    "footnote",
    "for",
    "foreging",
    "foregoing",
    "forgoing",
    "formerly",
    "formulation",
    "four",
    "friendly",
    "from",
    "full",
    "furnished",
    "further",
    "general",
    "geometer",
    "giving",
    "governed",
    "government",
    "governor",
    "granted",
    "handled",
    "have",
    "having",
    "heard",
    "hearing",
    "here",
    "his",
    "holding",
    "however",
    "immediately",
    "impose",
    "imposed",
    "increased",
    "indiana",
    "indicated",
    "indisposed",
    "individual",
    "indorsed",
    "industrial",
    "ing",
    "initial",
    "injunction",
    "insists",
    "instead",
    "insufficient",
    "interino",
    "intermediary",
    "intermediate",
    "interpretation",
    "intervention",
    "involves",
    "issuance",
    "issued",
    "issuing",
    "italic",
    "january",
    "join",
    "joined",
    "joining",
    "joins",
    "judge",
    "judgement",
    "judges",
    "judgment",
    "judicial",
    "jueces",
    "july",
    "june",
    "jurisdiction",
    "jus",
    "justice",
    "justices",
    "last",
    "late",
    "later",
    "law",
    "legally",
    "like",
    "limited",
    "lined",
    "made",
    "magistrate",
    "majority",
    "making",
    "march",
    "maryland",
    "may",
    "maybe",
    "member",
    "memorandum",
    "military",
    "modified",
    "motion",
    "moved",
    "much",
    "necessarily",
    "nonconcurring",
    "not",
    "note",
    "noted",
    "november",
    "now",
    "number",
    "occasionally",
    "october",
    "of",
    "off",
    "ohio",
    "once",
    "one",
    "only",
    "opened",
    "opinion",
    "opinions",
    "opposed",
    "opposing",
    "oral",
    "orally",
    "order",
    "ordered",
    "ordinance",
    "originally",
    "other",
    "otherwise",
    "out",
    "overruled",
    "page",
    "paid",
    "painter",
    "pair",
    "panel",
    "part",
    "parte",
    "participate",
    "participated",
    "participating",
    "participation",
    "passed",
    "per",
    "petition",
    "petitions",
    "place",
    "plaintiff",
    "plans",
    "plea",
    "policy",
    "posed",
    "possessed",
    "possession",
    "post",
    "pre",
    "precedent",
    "preceding",
    "precondition",
    "predomination",
    "prejudice",
    "prejudiced",
    "prejudicial",
    "premised",
    "premiums",
    "preparation",
    "prepared",
    "present",
    "presented",
    "preside",
    "president",
    "presidente",
    "presidents",
    "presiding",
    "presumption",
    "prevailed",
    "prevent",
    "prevention",
    "previously",
    "principal",
    "prior",
    "pro",
    "probation",
    "procedure",
    "proceed",
    "proceeded",
    "proceeding",
    "processing",
    "produced",
    "production",
    "profession",
    "pronounced",
    "properly",
    "proportion",
    "proposed",
    "proposition",
    "propositions",
    "prosecuting",
    "prosecution",
    "prosecutor",
    "prost",
    "protection",
    "prothonotary",
    "provided",
    "provident",
    "providential",
    "providing",
    "provision",
    "provisions",
    "publication",
    "published",
    "purchased",
    "put",
    "qualified",
    "quashing",
    "question",
    "questions",
    "raised",
    "reached",
    "read",
    "reargued",
    "reason",
    "reasoning",
    "reasons",
    "reassignment",
    "receiver",
    "recently",
    "recommendation",
    "recommended",
    "recorded",
    "recover",
    "recusal",
    "recuse",
    "recused",
    "reference",
    "referred",
    "refused",
    "rehearing",
    "rejected",
    "relating",
    "relief",
    "remained",
    "remaining",
    "remanded",
    "remarked",
    "rendered",
    "rendering",
    "report",
    "reported",
    "reporter",
    "reports",
    "representative",
    "representing",
    "requirements",
    "resentencing",
    "reservation",
    "resident",
    "resignation",
    "resigned",
    "resolved",
    "respectfully",
    "respecting",
    "respectively",
    "respondent",
    "response",
    "restraining",
    "resubmission",
    "resubmitted",
    "resul",
    "result",
    "retained",
    "retaliation",
    "retired",
    "retrospectively",
    "reversal",
    "reverse",
    "reversed",
    "reversing",
    "review",
    "right",
    "rilling",
    "ruling",
    "running",
    "rushing",
    "said",
    "sat",
    "saying",
    "sealed",
    "seasonably",
    "second",
    "secretary",
    "section",
    "see",
    "seeing",
    "sell",
    "senior",
    "sentencing",
    "separate",
    "separately",
    "september",
    "served",
    "several",
    "should",
    "signed",
    "signing",
    "since",
    "sit",
    "siting",
    "sitting",
    "sled",
    "solely",
    "some",
    "something",
    "special",
    "specially",
    "specifically",
    "standing",
    "start",
    "state",
    "stated",
    "statement",
    "states",
    "stating",
    "statute",
    "staying",
    "still",
    "stippling",
    "stipulated",
    "stipulation",
    "stockholder",
    "stockholders",
    "stopped",
    "submitted",
    "substantially",
    "substituting",
    "succeeded",
    "such",
    "sued",
    "suggested",
    "sumbitted",
    "summary",
    "superior",
    "supernumerary",
    "supervised",
    "supplemental",
    "supreme",
    "sure",
    "surely",
    "surrogate",
    "surrorrogate",
    "suspended",
    "suspending",
    "suspension",
    "sustained",
    "sustaining",
    "syllabus",
    "take",
    "taking",
    "tem",
    "temporarily",
    "temporary",
    "term",
    "termination",
    "territorial",
    "testify",
    "texas",
    "that",
    "the",
    "them",
    "themselves",
    "then",
    "thereafter",
    "therefor",
    "therefore",
    "therefrom",
    "thereof",
    "thereon",
    "thereto",
    "thes",
    "these",
    "think",
    "thinks",
    "this",
    "those",
    "though",
    "threatened",
    "three",
    "through",
    "time",
    "timely",
    "title",
    "today",
    "together",
    "tolling",
    "took",
    "top",
    "transfer",
    "transmission",
    "trended",
    "trial",
    "tribunal",
    "tried",
    "trying",
    "twelfth",
    "two",
    "unanimous",
    "unanimously",
    "unconstitutional",
    "under",
    "underline",
    "understanding",
    "united",
    "unjustified",
    "unknown",
    "unnecessary",
    "unpublished",
    "until",
    "untimely",
    "upon",
    "used",
    "vacancy",
    "vacated",
    "vacating",
    "veredict",
    "very",
    "vice",
    "views",
    "violating",
    "vol",
    "voluntarily",
    "voluntary",
    "voted",
    "votes",
    "voting",
    "waiting",
    "want",
    "war",
    "warden",
    "warranted",
    "was",
    "web",
    "were",
    "which",
    "while",
    "whole",
    "with",
    "without",
    "would",
    "writes",
    "writing",
    "written",
    "years",
    "yielded",
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
    require_living_judge: bool = True,
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
    :param require_living_judge: Whether to ensure that the judge found was
    born before the event date and died after it. In order to keep code simple,
    there's some slop in here to allow for date fields with low granularity
    (like those with DATE_GRANULARITY = "%Y").
    :return Either the judge that matched the name in the court at the right
    time, or None.
    """
    if isinstance(name, str):
        name = HumanName(name)

    filter_sets = []

    # check based on last name, court, and functioning flesh and blood first
    first_filter = [
        Q(name_last__iexact=name.last)
        | Q(aliases__name_last__iexact=name.last),
        Q(positions__court_id=court_id),
    ]
    if require_living_judge and event_date:
        first_filter.extend(
            [
                # Include timedelta here to account for low-granularity fields.
                # For example, if they died on 2021/10/15, but we only have the
                # granularity of a month, and the event is on 2021/10/14, then
                # date_dob would be 2021/10/01, and we'd miss this. Since
                # granularity can be off by as much as 365 days, just add some
                # slop into our query to make sure that when we have low
                # granularity, we err on the side of over-inclusion. Another
                # approach would be to factor in the granularity field and
                # adjust this accordingly, but that's harder.
                Q(date_dod__gte=event_date - timedelta(days=365))
                | Q(date_dod__isnull=True),
                Q(date_dob__lte=event_date + timedelta(days=365))
                | Q(date_dob__isnull=True),
            ]
        )
    filter_sets.append(first_filter)

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
        filter_sets.append(
            [
                Q(name_first__iexact=name.first)
                | Q(aliases__name_first__iexact=name.first)
            ]
        )

    # Do middle name or initial next.
    if name.middle:
        stripped_middle = name.middle.strip(".,")
        initial = len(stripped_middle) == 1
        if initial:
            filter_sets.append(
                [
                    Q(name_middle__istartswith=stripped_middle)
                    | Q(aliases__name_middle__istartswith=stripped_middle)
                ]
            )
        else:
            filter_sets.append(
                [
                    Q(name_middle__iexact=name.middle)
                    | Q(aliases__name_middle__iexact=name.middle)
                ]
            )

    # And finally, by suffix
    if name.suffix:
        suffix = SUFFIX_LOOKUP.get(name.suffix.lower())
        if suffix:
            filter_sets.append(
                [
                    Q(name_suffix__iexact=suffix)
                    | Q(aliases__name_suffix__iexact=suffix)
                ]
            )

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
    full_name: Union[HumanName, str],
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
    require_living_judge: bool = True,
) -> Optional[Person]:
    """Look up the judge using their last name, a date and court"""
    hn = HumanName()
    hn.last = last_name
    return lookup_judge_by_full_name(
        hn, court_id, event_date, require_living_judge
    )


def lookup_judges_by_last_name_list(
    last_names: List[str],
    court_id: str,
    event_date: Optional[date] = None,
    require_living_judge: bool = True,
) -> List[Person]:
    """Look up a group of judges by list of last names, a date, and a court"""
    found_people = []
    for last_name in last_names:
        hn = HumanName()
        hn.last = last_name
        person = lookup_judge_by_full_name(
            hn, court_id, event_date, require_living_judge
        )
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


def sort_judge_list(judges: QuerySet, search_terms: Set[str]) -> QuerySet:
    """Filter a list of judges by a set of search terms.

    This method counts exact hits on first middle last suffix and returns
    an ordered queryset of judges with the most paritial/full matches.

    :param judges: Queryset of judges found with matching names
    :param search_terms: Set of search terms for looking up judges by name
    :return: Best queryset of judges ordered by last name
    """
    judge_dict = {}
    highest_match = 0
    for judge in judges:
        judge_names = {
            judge.name_first,
            judge.name_last,
            judge.name_middle,
            judge.name_suffix,
        }

        count = 0
        for term in search_terms:
            for name in judge_names:
                if term.lower() in name.lower():
                    count += 1

        if count > highest_match:
            highest_match = count
        if count == highest_match:
            judge_dict[judge.id] = count

    # Create list of Judge IDs that have the highest match count
    judge_pks = []
    for k, v in judge_dict.items():
        if v == highest_match:
            judge_pks.append(k)

    # Return the filtered queryset and sort by name_last
    return judges.filter(pk__in=judge_pks).order_by("name_last")


def lookup_judge_by_name_components(queryset: QuerySet, s: str) -> QuerySet:
    """Find judges by first, middle, last name or suffix.

    :param queryset: Queryset to filter
    :param s: User search terms in financial disclosures lookup by judge
    :return: Filter Queryset
    """
    # Possible DOS attack. Don't hit the DB.
    search_terms = s.split()[:7]
    search_args = []
    for term in search_terms:
        for query in (
            "name_first__istartswith",
            "name_last__istartswith",
            "name_middle__istartswith",
            "name_suffix__istartswith",
        ):
            search_args.append(Q(**{query: term}))
    judges = queryset.filter(reduce(operator.or_, search_args))
    return sort_judge_list(judges, set(search_terms))

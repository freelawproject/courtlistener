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
    "ability",
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
    "accordance",
    "according",
    "accordingly",
    "accounting",
    "accurately",
    "accused",
    "acknowledged",
    "acordó",
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
    "advocate",
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
    "alabama",
    "alienation",
    "all",
    "allocation",
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
    "announced",
    "announcement",
    "announcing",
    "annually",
    "another",
    "answer",
    "any",
    "apart",
    "apparent",
    "appeal",
    "appealability",
    "appealed",
    "appeals",
    "appearance",
    "appeared",
    "appearing",
    "appears",
    "appellant",
    "appellants",
    "appellate",
    "appellee",
    "appendix",
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
    "appropriation",
    "approval",
    "approved",
    "april",
    "arbitration",
    "are",
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
    "assigns",
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
    "background",
    "balance",
    "baltimore",
    "banc",
    "bankruptcy",
    "based",
    "became",
    "because",
    "been",
    "before",
    "behalf",
    "behavior",
    "being",
    "believe",
    "believes",
    "believing",
    "belonged",
    "belonging",
    "below",
    "besides",
    "between",
    "beyond",
    "big",
    "board",
    "bold",
    "boring",
    "both",
    "briefing",
    "briefs",
    "but",
    "california",
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
    "central",
    "certification",
    "certified",
    "ch",
    "chairman",
    "chancellor",
    "changing",
    "chapter",
    "character",
    "charge",
    "charging",
    "chief",
    "circuit",
    "circumstances",
    "cited",
    "city",
    "claims",
    "clarification",
    "close",
    "closed",
    "coincided",
    "columbia",
    "coming",
    "commandant",
    "commander",
    "comment",
    "commerce",
    "commercial",
    "commisioners",
    "commission",
    "commissioner",
    "commissioners",
    "commissions",
    "committed",
    "commodity",
    "common",
    "companion",
    "company",
    "comparative",
    "compensation",
    "competency",
    "compiled",
    "complainant",
    "complained",
    "complaint",
    "completed",
    "completion",
    "composed",
    "compromise",
    "compromised",
    "concealing",
    "concerned",
    "concerning",
    "concerring",
    "conclude",
    "concluding",
    "conclusion",
    "conclusions",
    "concur",
    "concurred",
    "concurrence",
    "concurrentes",
    "concurrently",
    "concurring",
    "concurs",
    "condition",
    "conditioned",
    "conditions",
    "conducted",
    "conducting",
    "conference",
    "conferences",
    "conferring",
    "confessed",
    "confession",
    "confirmed",
    "connected",
    "consecutively",
    "consent",
    "consequence",
    "consider",
    "consideration",
    "considered",
    "considering",
    "consist",
    "consisted",
    "consistent",
    "consisting",
    "consists",
    "consolidated",
    "consolidation",
    "constable",
    "constitute",
    "constituting",
    "constitution",
    "constitutional",
    "construction",
    "consultation",
    "contained",
    "contemplated",
    "contends",
    "continue",
    "continued",
    "contract",
    "contradiction",
    "contrary",
    "control",
    "controls",
    "controversy",
    "convened",
    "conversion",
    "convicting",
    "conviction",
    "coordinator",
    "corporation",
    "corporations",
    "correct",
    "costs",
    "course",
    "court",
    "credit",
    "criminal",
    "curiam",
    "customers",
    "customs",
    "dated",
    "day",
    "deadline",
    "deceased",
    "decedent",
    "december",
    "decided",
    "deciding",
    "decision",
    "declaration",
    "declarations",
    "declaring",
    "declined",
    "declining",
    "defendant",
    "defendants",
    "defense",
    "deliberations",
    "delivered",
    "delivering",
    "denial",
    "denials",
    "denied",
    "deny",
    "denying",
    "department",
    "deputy",
    "describing",
    "deserving",
    "designated",
    "designation",
    "desiring",
    "destination",
    "determination",
    "determined",
    "determining",
    "development",
    "did",
    "died",
    "difference",
    "directed",
    "directly",
    "disciplinary",
    "discipline",
    "disclosed",
    "discontinuance",
    "discretion",
    "discretionary",
    "discrimination",
    "discussed",
    "discussing",
    "discussions",
    "dismiss",
    "dismissal",
    "dismissed",
    "dismissing",
    "disposed",
    "disposition",
    "disqualification",
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
    "employed",
    "employment",
    "enforced",
    "enforcement",
    "engaged",
    "entered",
    "entirely",
    "entitled",
    "entry",
    "eoncurring",
    "equally",
    "equity",
    "error",
    "espoused",
    "establish",
    "established",
    "even",
    "ever",
    "examination",
    "exceed",
    "except",
    "excepting",
    "exclusively",
    "excused",
    "executed",
    "execution",
    "exempt",
    "exercised",
    "exist",
    "existed",
    "existence",
    "existing",
    "expedited",
    "explained",
    "expressed",
    "expressing",
    "extension",
    "facts",
    "failed",
    "favour",
    "february",
    "federal",
    "fellows",
    "few",
    "fifth",
    "filed",
    "final",
    "first",
    "five",
    "florida",
    "following",
    "footnote",
    "for",
    "foreging",
    "foregoing",
    "forgoing",
    "formerly",
    "formulation",
    "four",
    "fourth",
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
    "honorable",
    "however",
    "immediately",
    "impose",
    "imposed",
    "imposition",
    "impossible",
    "imprisonment",
    "improvements",
    "improvidently",
    "income",
    "increased",
    "indefinitely",
    "indiana",
    "indicated",
    "indisposed",
    "indisposition",
    "individual",
    "indorsed",
    "industrial",
    "ing",
    "initial",
    "injunction",
    "insists",
    "instead",
    "instruction",
    "instructions",
    "instrument",
    "insufficient",
    "insurance",
    "intent",
    "intention",
    "interest",
    "interested",
    "interests",
    "interino",
    "intermediary",
    "intermediate",
    "interpretation",
    "intervention",
    "intervinieron",
    "introduction",
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
    "journal",
    "judge",
    "judged",
    "judgement",
    "judges",
    "judgment",
    "judicial",
    "jueces",
    "july",
    "june",
    "jurisdiction",
    "jurisdictional",
    "jus",
    "justice",
    "justices",
    "last",
    "late",
    "later",
    "law",
    "learned",
    "legally",
    "legislature",
    "lifetime",
    "like",
    "limitation",
    "limitations",
    "limited",
    "lined",
    "made",
    "magistrate",
    "majority",
    "making",
    "march",
    "maryland",
    "massachusetts",
    "material",
    "may",
    "maybe",
    "meaning",
    "member",
    "memorandum",
    "mexico",
    "military",
    "misconduct",
    "modification",
    "modified",
    "motion",
    "moved",
    "much",
    "municipal",
    "necessarily",
    "negative",
    "nonconcurring",
    "not",
    "note",
    "noted",
    "notice",
    "november",
    "now",
    "number",
    "occasionally",
    "occasioned",
    "october",
    "of",
    "off",
    "ohio",
    "once",
    "one",
    "only",
    "opened",
    "operated",
    "opinion",
    "opinions",
    "opposed",
    "opposing",
    "oral",
    "orally",
    "order",
    "ordered",
    "orders",
    "ordinance",
    "original",
    "originally",
    "other",
    "others",
    "otherwise",
    "out",
    "overruled",
    "page",
    "paid",
    "painter",
    "pair",
    "panel",
    "paragraph",
    "paragraphs",
    "part",
    "parte",
    "partial",
    "participate",
    "participated",
    "participating",
    "participation",
    "parties",
    "passed",
    "payments",
    "pending",
    "pennsylvania",
    "per",
    "performance",
    "petition",
    "petitioners",
    "petitions",
    "place",
    "plaintiff",
    "plans",
    "plastics",
    "plea",
    "pleading",
    "policy",
    "posed",
    "possessed",
    "possession",
    "post",
    "prayers",
    "pre",
    "precedent",
    "preceding",
    "precondition",
    "predomination",
    "preference",
    "prejudice",
    "prejudiced",
    "prejudicial",
    "preliminary",
    "premised",
    "premises",
    "premiums",
    "preparation",
    "prepared",
    "prerequisites",
    "present",
    "presented",
    "presents",
    "preside",
    "presided",
    "president",
    "presidente",
    "presidents",
    "presiding",
    "presumption",
    "prevailed",
    "prevent",
    "prevented",
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
    "proceedings",
    "proceeds",
    "processing",
    "produced",
    "production",
    "profession",
    "prohibition",
    "promise",
    "pronounced",
    "properly",
    "proportion",
    "proposed",
    "proposition",
    "propositions",
    "prosecuting",
    "prosecution",
    "prosecutor",
    "prospective",
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
    "purposes",
    "put",
    "qualified",
    "quashing",
    "question",
    "questions",
    "raised",
    "re",
    "reached",
    "read",
    "realized",
    "reargued",
    "reargument",
    "reason",
    "reasoning",
    "reasons",
    "reassigned",
    "reassignment",
    "receiver",
    "receiving",
    "recently",
    "recognized",
    "recommendation",
    "recommended",
    "recorded",
    "recover",
    "recovery",
    "recusal",
    "recuse",
    "recused",
    "reference",
    "referred",
    "refused",
    "regarding",
    "registration",
    "regulation",
    "rehearing",
    "reinstated",
    "reinstatement",
    "rejected",
    "relating",
    "relation",
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
    "representatives",
    "represented",
    "representing",
    "reputation",
    "requirement",
    "requirements",
    "resentencing",
    "reservation",
    "resident",
    "resignation",
    "resigned",
    "resolution",
    "resolved",
    "respectfully",
    "respecting",
    "respectively",
    "respondent",
    "response",
    "restitution",
    "restraining",
    "resubmission",
    "resubmitted",
    "resul",
    "result",
    "retained",
    "retaliation",
    "retired",
    "retrospectively",
    "returned",
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
    "secretario",
    "secretary",
    "section",
    "sections",
    "see",
    "seeing",
    "sell",
    "senate",
    "senior",
    "sentence",
    "sentences",
    "sentencing",
    "separate",
    "separately",
    "september",
    "served",
    "setting",
    "settlement",
    "several",
    "sheriff",
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
    "submission",
    "submitted",
    "substantially",
    "substituting",
    "succeeded",
    "such",
    "sued",
    "sufficient",
    "sufficiently",
    "suggested",
    "suggestion",
    "suggestions",
    "sumbitted",
    "summary",
    "superior",
    "supernumerary",
    "supervised",
    "supervisory",
    "supplement",
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
    "telephone",
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
    "transaction",
    "transactions",
    "transfer",
    "transferred",
    "transmission",
    "transportation",
    "trended",
    "trial",
    "tribunal",
    "tried",
    "trying",
    "twelfth",
    "two",
    "unanimous",
    "unanimously",
    "unavailability",
    "unconstitutional",
    "under",
    "underline",
    "understanding",
    "understood",
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
    "violations",
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
    "workers",
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

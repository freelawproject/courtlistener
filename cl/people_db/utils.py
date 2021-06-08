import html
import re
from typing import List

from django.utils.html import strip_tags

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
            first_last = "%s %s" % (names[i - 1], names[i])
            first_m_last = r"%s [a-z]\.? %s" % (names[i - 1], names[i])
            if re.search("%s|%s" % (first_last, first_m_last), text):
                last_names[-1] = names[i]
                continue
            last_names.append(names[i])
    return last_names

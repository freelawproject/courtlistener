import copy
import itertools
import os
import re
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from glob import glob
from typing import Any

from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup, Tag
from django.core.files.base import ContentFile
from django.core.management import CommandError, CommandParser
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from eyecite.find import get_citations
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer
from juriscraper.lib.string_utils import (
    CaseNameTweaker,
    convert_date_string,
    harmonize,
    titlecase,
)

from cl.corpus_importer.management.commands.harvard_opinions import (
    find_previously_imported_cases,
    map_opinion_type,
    parse_extra_fields,
)
from cl.corpus_importer.utils import (
    add_citations_to_cluster,
    clean_body_content,
    get_court_id,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1
from cl.lib.storage import ScanningFinalXmlStorage
from cl.lib.url_utils import BASE_URL
from cl.lib.utils import human_sort
from cl.people_db.lookup_utils import (
    extract_judge_last_name,
    lookup_judges_by_messy_str,
)
from cl.scrapers.utils import (
    case_names_are_too_different,
    update_or_create_docket,
)
from cl.search.cluster_sources import ClusterSources
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    OpinionContent,
)

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")

cnt = CaseNameTweaker()

# The scanning portal stores one XML per approved opinion at
# export/{scan id}/{opinion id}.xml in its private bucket
FINAL_XML_PREFIX = "export/"
# The `schema` attribute values of `<casebody>` this command knows how to
# read. The portal raises it when its output changes shape.
SUPPORTED_SCHEMAS = {"1"}

PER_CURIAM_RE = re.compile(r"per\s+curiam", re.IGNORECASE)
# A complete date as printed in reporters: "May 22, 2024", "Dec. 18, 2009",
# "Sept. 3, 2024" or "5/22/2024"
FULL_DATE_PATTERN = (
    r"\b(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b"
)
FULL_DATE_RE = re.compile(FULL_DATE_PATTERN, re.IGNORECASE)
# Dates labeled as the decision date, e.g. "Decided May 22, 2024",
# "Decided on May 22, 2024", "Decided - May 22, 2024" or "Opinion filed
# May 22, 2024". Other dates printed in the same element, like "Argued" or
# "Rehearing Denied", may come before them.
DATE_LABEL_SEPARATOR = r"[\s.:,\-\u2013\u2014]*(?:on\s+)?"
DECIDED_DATE_RE = re.compile(
    rf"\bdecided\b{DATE_LABEL_SEPARATOR}({FULL_DATE_PATTERN})",
    re.IGNORECASE,
)
FILED_DATE_RE = re.compile(
    rf"\bfiled\b{DATE_LABEL_SEPARATOR}({FULL_DATE_PATTERN})", re.IGNORECASE
)
# The "No." or "Case No." printed before docket numbers
DOCKET_NUMBER_PREFIX_RE = re.compile(
    r"^(?:case\s+)?nos?(?:\.\s*|\s+)", re.IGNORECASE
)

# Words that should stay lowercase in case names when printed in caps.
LOWERCASE_CASE_NAME_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "re",
    "the",
    "to",
}
# Acronyms with vowels that should stay in caps. Words without vowels, like
# "LLC", are always taken as acronyms.
CASE_NAME_ACRONYMS = {"USA", "IV", "NA", "PA", "UAW", "AFL", "CIO"}
# Abbreviations without vowels that are not acronyms, e.g. "JR." -> "Jr."
CASE_NAME_ABBREVIATIONS = {
    "DR",
    "FT",
    "JR",
    "LTD",
    "MR",
    "MRS",
    "MS",
    "MT",
    "SR",
    "ST",
}
# Roman numerals up to 39, e.g. "VIII". `titlecase` only keeps II and III.
ROMAN_NUMERAL_RE = re.compile(r"(?=[IVX])X{0,3}(?:IX|IV|V?I{0,3})")
# Vowels, including the accented capitals of names like "PAGÁN"
CAPITAL_VOWEL_RE = re.compile(r"[AEIOUYÀ-ÆÈ-ÏÒ-ÖØ-Ý]")
# Comma-separated parts of a caption party that are still its name, like
# "ex rel. Oklahoma Bar Association", "Jr." or "LLC". Other parts are the
# party's role or a description: "Appellant (Defendant)", "Trustee of ...".
PARTY_NAME_PART_RE = re.compile(
    r"^(?:ex\s+rel\.|jr\.?|sr\.?|[ivx]+|inc\.?|l\.?l\.?c\.?|l\.?l\.?p\.?"
    r"|ltd\.?|corp\.?|co\.?|n\.a\.|p\.a\.|p\.c\.|pllc)(?:\s|$)",
    re.IGNORECASE,
)

# Reporters of opinions that are never precedential
UNPUBLISHED_REPORTERS = {"F. App'x"}
# Notices printed on opinions without precedential effect, e.g. "NOT
# PRECEDENTIAL", "Not for publication" or "Rulings by summary order do not
# have precedential effect"
UNPUBLISHED_NOTICE_RE = re.compile(
    r"\bnot\s+(?:designated\s+)?for\s+(?:official\s+)?publication"
    r"|\b(?:not|non)[\s-]precedential"
    r"|\bunpublished\s+(?:opinion|decision|disposition|order)\b"
    r"|\bdoes?\s+not\s+have\s+precedential\s+(?:effect|value)"
    r"|\bsummary\s+order\b",
    re.IGNORECASE,
)
# How much of the start of the first opinion is searched for the notice.
# Further in, "unpublished" is likely a citation to another opinion.
UNPUBLISHED_NOTICE_SPAN = 2000

# Head matter elements kept out of `OpinionCluster.headmatter`, since the
# opinion page shows them from their own field
HEADMATTER_EXCLUDED = {"syllabus"}

# Cluster fields that come from the head matter of the XML. When merging
# into an existing cluster, only empty values are filled from the scan.
SHORT_FIELDS = {
    "attorneys": "attorneys",
    "disposition": "disposition",
    "otherdate": "other_dates",
}
LONG_FIELDS = {
    "syllabus": "syllabus",
    "summary": "summary",
    "history": "history",
    "headnotes": "headnotes",
}


@dataclass
class ScanCase:
    """Metadata and opinions parsed from a scanning project final XML."""

    xml: str
    scan_id: str
    scan_opinion_id: str
    case_name: str
    case_name_short: str
    case_name_full: str
    docket_number: str
    court: Court
    date_filed: date
    parsed_citations: list[FullCaseCitation]
    judges: str
    body_characters: str
    precedential_status: str = PRECEDENTIAL_STATUS.PUBLISHED
    page_count: int | None = None
    cluster_fields: dict[str, str] = field(default_factory=dict)
    opinions: list[Tag] = field(default_factory=list)

    @property
    def citation(self) -> FullCaseCitation:
        """The first citation of the scanned opinion."""
        return self.parsed_citations[0]

    @property
    def citations(self) -> list[str]:
        """Every citation of the scanned opinion, one per string.

        A `<citation>` element can hold parallel citations, e.g.
        "388 So. 3d 1, 2024 WL 2312345", but helpers like
        `add_citations_to_cluster` only read the first citation of a string.
        """
        return [cite.corrected_citation() for cite in self.parsed_citations]

    @property
    def file_name_prefix(self) -> str:
        """The start of the stored XML file name, unique to the opinion.

        e.g. "3593-12-" for opinion 12 of scan 3593
        """
        return f"{self.scan_id}-{self.scan_opinion_id}-"

    @property
    def file_name(self) -> str:
        """The name used to store the XML in `filepath_xml_scan`.

        e.g. "3593-12-388-so-3d-1.xml" for opinion 12 of scan 3593, at
        388 So. 3d 1. The ids identify the scanned opinion when it's imported
        again, and keep opinions that share a page from sharing a name.
        """
        citation_slug = slugify(self.citation.corrected_citation())
        return f"{self.file_name_prefix}{citation_slug}.xml"


def xml_file_paths(path: str) -> list[str]:
    """List the XML files to import, sorted the way humans expect.

    :param path: A single XML file, or a directory searched recursively.
    :return: A list of XML file paths.
    """
    if os.path.isfile(path):
        return [path]
    return human_sort(glob(os.path.join(path, "**", "*.xml"), recursive=True))


def s3_xml_keys(
    storage: ScanningFinalXmlStorage,
    scan_ids: list[str] | None,
    opinion_id: str | None = None,
) -> list[str]:
    """List the keys of the final XML files to import from the bucket.

    :param storage: The scanning portal's bucket.
    :param scan_ids: The scans to import. When empty, every scan with an
        exported XML.
    :param opinion_id: A single opinion of the only scan in `scan_ids`.
    :return: A list of S3 keys, e.g. "export/15343/3.xml".
    """
    if opinion_id and scan_ids:
        return [f"{FINAL_XML_PREFIX}{scan_ids[0]}/{opinion_id}.xml"]
    if not scan_ids:
        scan_ids, _ = storage.listdir(FINAL_XML_PREFIX)
    keys = []
    for scan_id in human_sort(scan_ids):
        _, file_names = storage.listdir(f"{FINAL_XML_PREFIX}{scan_id}/")
        keys.extend(
            f"{FINAL_XML_PREFIX}{scan_id}/{name}"
            for name in human_sort(file_names)
            if name.endswith(".xml")
        )
    return keys


def read_s3_xml(storage: ScanningFinalXmlStorage, key: str) -> str:
    """Read a final XML file from the scanning portal's bucket.

    :param storage: The scanning portal's bucket.
    :param key: The S3 key of the file.
    :return: The XML content.
    """
    with storage.open(key) as f:
        return f.read().decode("utf-8")


def read_local_xml(file_path: str) -> str:
    """Read a final XML file from the local disk.

    :param file_path: The path of the file.
    :return: The XML content.
    """
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def get_citation_strings(soup: BeautifulSoup) -> list[str]:
    """Get the citations of a scanned opinion from its `<citation>` elements.

    :param soup: The parsed XML.
    :return: A list of citation strings.
    """
    return [
        cite
        for element in soup.select("citation")
        if (cite := element.get_text(" ", strip=True))
    ]


def get_element_text(soup: BeautifulSoup, selector: str, sep: str) -> str:
    """Join the text of all elements matching a selector.

    :param soup: The parsed XML.
    :param selector: CSS selector of the elements.
    :param sep: The separator used to join the texts of multiple elements.
    :return: The joined text, or an empty string.
    """
    texts = [e.get_text(" ", strip=True) for e in soup.select(selector)]
    return sep.join(t for t in texts if t)


def get_docket_number(soup: BeautifulSoup) -> str:
    """Get the docket number without the printed prefix.

    e.g. "No. 4D2023-2459." becomes "4D2023-2459", which is the format
    scrapers store, so existing dockets can be found.

    :param soup: The parsed XML.
    :return: The docket numbers joined by "; ", or an empty string.
    """
    numbers = [
        DOCKET_NUMBER_PREFIX_RE.sub("", e.get_text(" ", strip=True)).strip(
            " ."
        )
        for e in soup.select("docketnumber")
    ]
    return "; ".join(n for n in numbers if n)


def _capitalize_caps_word(word: str) -> str:
    """Capitalize a word printed in caps, keeping its punctuation.

    e.g. "O'BRIEN" -> "O'Brien", "SMITH-JONES," -> "Smith-Jones,",
    "STATE'S" -> "State's"

    :param word: A word in capital letters.
    :return: The capitalized word.
    """
    word = re.sub(r"[^\W\d_]+", lambda m: m.group().capitalize(), word)
    return re.sub(r"'S\b", "'s", word)


def normalize_case_name_caps(case_name: str) -> str:
    """Titlecase the words a reporter printed in capital letters.

    Reporters print party names in small caps, so the OCR text looks like
    "Larry B. MERRITT v. STATE of Florida". `titlecase` treats all-caps words
    as acronyms and keeps them, so they are fixed here first.

    Caveat: an all-caps word is kept as an acronym only when it has no
    vowels (LLC) or is in CASE_NAME_ACRONYMS, so other acronyms like "ABC"
    become "Abc".

    :param case_name: The case name.
    :return: The case name with normalized capitalization.
    """
    words = []
    for word in case_name.split():
        letters = "".join(filter(str.isalpha, word))
        if mc_name := re.fullmatch(r"(Mc|Mac)([A-Z]{2,})", letters):
            # e.g. McDONALD
            word = word.replace(
                mc_name.group(2), mc_name.group(2).capitalize(), 1
            )
        elif letters.isupper():
            is_acronym = (
                letters in CASE_NAME_ACRONYMS
                or ROMAN_NUMERAL_RE.fullmatch(letters)
                or not CAPITAL_VOWEL_RE.search(letters)
            )
            if letters.lower() in LOWERCASE_CASE_NAME_WORDS:
                word = word.lower()
            elif letters in CASE_NAME_ABBREVIATIONS or not is_acronym:
                word = _capitalize_caps_word(word)
        words.append(word)
    # titlecase capitalizes "re" and "ex rel.", but CL uses "In re" and
    # "ex rel."
    case_name = re.sub(r"\bIn Re\b", "In re", titlecase(" ".join(words)))
    return re.sub(r"\bEx Rel\b", "ex rel", case_name)


def get_party_sides(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """Get the caption's parties on each side of its "v." separator.

    The parties are usually in `<parties>`, but some captions are a
    paragraph of `<party>` elements without it.

    :param soup: The parsed XML.
    :return: The texts of the parties before and after the separator.
    """
    if (parties := soup.select_one("parties")) is None:
        first_party = next(
            (p for p in soup.select("party") if not p.find_parent("opinion")),
            None,
        )
        parties = first_party.parent if first_party else None
    sides: tuple[list[str], list[str]] = ([], [])
    if parties is None:
        return sides
    side = 0
    for element in parties.find_all(["party", "separator"]):
        if element.name == "separator":
            side = 1
        elif text := element.get_text(" ", strip=True):
            sides[side].append(text)
    return sides


def get_party_name(party: str) -> str:
    """Get the name of the first party in a caption party's text.

    e.g. "Cody Allan KOTRC, Appellant (Defendant)," -> "Cody Allan KOTRC",
    "Ashton ORR; Zaya Perysian, Plaintiffs," -> "Ashton ORR", and
    "STATE of Oklahoma, EX REL. OKLAHOMA BAR ASSOCIATION, Complainant," ->
    "STATE of Oklahoma, EX REL. OKLAHOMA BAR ASSOCIATION"

    :param party: The text of a `<party>` element.
    :return: The party's name, without its role or description.
    """
    first = re.sub(r"\([^)]*\)", "", party.split(";")[0])
    name, *parts = [part.strip() for part in first.split(",")]
    for part in parts:
        if not PARTY_NAME_PART_RE.match(part):
            break
        name = f"{name}, {part}"
    return re.sub(r"^the\s+", "", name.strip(" ,"), flags=re.IGNORECASE)


def get_case_names(soup: BeautifulSoup) -> tuple[str, str]:
    """Get the case name and the full case name from the caption.

    The case name uses the first party on each side, e.g. "Cheri Lynn
    Marler v. State of Wyoming"; the full name is the whole caption.

    :param soup: The parsed XML.
    :return: The case name and the full case name, or empty strings when
        the XML has no parties.
    """
    left, right = get_party_sides(soup)
    if not left:
        return "", ""
    names = [get_party_name(side[0]) for side in (left, right) if side]
    case_name = normalize_case_name_caps(harmonize(" v. ".join(names)))
    caption = " ".join(left)
    if right:
        caption = f"{caption} v. {' '.join(right)}"
    return case_name, normalize_case_name_caps(caption.strip(". "))


def get_headmatter(soup: BeautifulSoup) -> str:
    """Get the head matter: the `<casebody>` elements before its opinions.

    Wrapped in `<headmatter>` for `OpinionCluster.headmatter`, so the
    citation, parties, docket number, court, dates, attorneys and the rest
    can be shown above the opinions. Their values are also stored in their
    own fields. Elements in HEADMATTER_EXCLUDED are left out.

    Caveat: call it before `parse_extra_fields`, which removes the page
    numbers from the elements it reads.

    :param soup: The parsed XML.
    :return: The head matter XML, or an empty string if there is none.
    """
    if (casebody := soup.select_one("casebody")) is None:
        return ""
    elements = []
    for element in casebody.find_all(recursive=False):
        if element.name == "opinion":
            break
        if element.name not in HEADMATTER_EXCLUDED:
            elements.append(str(element))
    if not elements:
        return ""
    return "<headmatter>\n{}\n</headmatter>".format("\n".join(elements))


def get_precedential_status(
    soup: BeautifulSoup, citations: list[FullCaseCitation]
) -> str:
    """Tell whether the scanned opinion is published or unpublished.

    Unpublished when its reporter only prints unpublished opinions, like
    F. App'x, or when the head matter or the start of the first opinion
    prints a notice like "NOT PRECEDENTIAL" or "Not for publication".

    Caveat: a notice deep in the opinion is not found, so that a
    published opinion citing an "unpublished opinion" stays published.

    :param soup: The parsed XML.
    :param citations: The parsed citations of the opinion.
    :return: A PRECEDENTIAL_STATUS value.
    """
    if any(c.corrected_reporter() in UNPUBLISHED_REPORTERS for c in citations):
        return PRECEDENTIAL_STATUS.UNPUBLISHED
    casebody = soup.select_one("casebody")
    head = []
    if casebody is not None:
        for element in casebody.find_all(recursive=False):
            if element.name == "opinion":
                head.append(element.get_text(" ")[:UNPUBLISHED_NOTICE_SPAN])
                break
            head.append(element.get_text(" "))
    if UNPUBLISHED_NOTICE_RE.search(" ".join(head)):
        return PRECEDENTIAL_STATUS.UNPUBLISHED
    return PRECEDENTIAL_STATUS.PUBLISHED


def get_date_filed(soup: BeautifulSoup) -> date | None:
    """Parse the decision date of the scanned opinion.

    Books print it in brackets, e.g. "[May 22, 2024]", or with other dates,
    e.g. "Argued Oct. 3, 2023. Decided May 22, 2024." Uses the first date
    labeled "Decided" in the `<decisiondate>` elements, else the first one
    labeled "Filed", since a motion can be filed after the decision, else
    their first complete date. Partial dates like "May 2024" are rejected
    instead of guessing the missing day.

    :param soup: The parsed XML.
    :return: The decision date, or None if it can't be parsed.
    """
    texts = [e.get_text(" ") for e in soup.select("decisiondate")]
    for date_re, group in (
        (DECIDED_DATE_RE, 1),
        (FILED_DATE_RE, 1),
        (FULL_DATE_RE, 0),
    ):
        for text in texts:
            for match in date_re.finditer(text):
                # Normalize "Sept." since dateutil only knows "Sep"
                date_text = re.sub(r"(?i)\bsept\b", "Sep", match.group(group))
                try:
                    return convert_date_string(date_text)
                except (ValueError, OverflowError):
                    # e.g. an OCR error like "Feb. 30, 2024"
                    continue
    return None


def get_page_count(soup: BeautifulSoup) -> int | None:
    """Get the number of printed pages of the casebody.

    :param soup: The parsed XML.
    :return: The page count, or None if the page attributes are missing.
    """
    casebody = soup.select_one("casebody")
    if not casebody:
        return None
    first_page, last_page = casebody.get("firstpage"), casebody.get("lastpage")
    if not (
        isinstance(first_page, str)
        and isinstance(last_page, str)
        and first_page.isdigit()
        and last_page.isdigit()
    ):
        return None
    return int(last_page) - int(first_page) + 1


def get_judges(soup: BeautifulSoup) -> str:
    """Get the judges names from the `judges` and `author` elements.

    :param soup: The parsed XML.
    :return: A comma separated, deduplicated and sorted list of last names.
    """
    names = [
        extract_judge_last_name(e.get_text(" ", strip=True))
        for e in soup.select("judges, author")
    ]
    return titlecase(
        ", ".join(sorted(set(itertools.chain.from_iterable(names))))
    )


def parse_scan_xml(
    xml: str,
    file_path: str,
    court_id: str | None,
) -> ScanCase | None:
    """Parse a scanning project final XML into a ScanCase.

    Logs a warning and returns None when the XML lacks data required to
    import it: opinion, parties, date, court or citation.

    :param xml: The XML content.
    :param file_path: The path of the XML file, used for logging.
    :param court_id: The CL court id. When None, it is looked up with
        courts-db from the `court` element.
    :return: A ScanCase, or None if the file can't be imported.
    """
    soup = BeautifulSoup(xml, "lxml-xml")

    casebody = soup.select_one("casebody")
    schema = casebody.get("schema") if casebody else None
    if casebody is None or schema not in SUPPORTED_SCHEMAS:
        logger.warning(
            "Unsupported schema %s in %s. Supported: %s",
            schema,
            file_path,
            sorted(SUPPORTED_SCHEMAS),
        )
        return None

    scan_id, scan_opinion_id = (
        casebody.get("scan-id"),
        casebody.get("opinion-id"),
    )
    if not (
        isinstance(scan_id, str)
        and scan_id
        and isinstance(scan_opinion_id, str)
        and scan_opinion_id
    ):
        logger.warning("Missing scan-id or opinion-id in %s", file_path)
        return None

    # Copy the opinion XML before `parse_extra_fields` mutates the soup
    opinions = [copy.copy(op) for op in soup.select("opinion")]
    if not opinions:
        logger.warning("No opinion found in %s", file_path)
        return None
    headmatter = get_headmatter(soup)

    case_name, case_name_full = get_case_names(soup)
    if not case_name:
        logger.warning("No parties found in %s", file_path)
        return None

    if not (date_filed := get_date_filed(soup)):
        logger.warning(
            "Can't parse date '%s' in %s",
            get_element_text(soup, "decisiondate", " "),
            file_path,
        )
        return None

    if not court_id:
        court_text = get_element_text(soup, "court", " ")
        found_courts = get_court_id(court_text)
        if len(found_courts) != 1:
            logger.warning(
                "Court not found for '%s' in %s. Found: %s",
                court_text,
                file_path,
                found_courts,
            )
            return None
        court_id = found_courts[0]
    if not (court := Court.objects.filter(id=court_id).first()):
        logger.warning("Court not found in CourtListener: %s", court_id)
        return None

    cite_strings = get_citation_strings(soup)
    cites = [
        cite
        for cite_str in cite_strings
        for cite in get_citations(
            re.sub(r"\s+", " ", cite_str), tokenizer=HYPERSCAN_TOKENIZER
        )
        if isinstance(cite, FullCaseCitation)
    ]
    if not cites:
        logger.warning("No valid citation %s in %s", cite_strings, file_path)
        return None

    short_data = parse_extra_fields(soup, list(SHORT_FIELDS), False)
    long_data = parse_extra_fields(soup, list(LONG_FIELDS), True)
    cluster_fields = {
        SHORT_FIELDS.get(name) or LONG_FIELDS[name]: value
        for name, value in {**short_data, **long_data}.items()
        if value
    }
    if headmatter:
        cluster_fields["headmatter"] = headmatter

    return ScanCase(
        xml=xml,
        scan_id=scan_id,
        scan_opinion_id=scan_opinion_id,
        case_name=case_name,
        case_name_short=cnt.make_case_name_short(case_name),
        case_name_full=case_name_full,
        docket_number=get_docket_number(soup),
        court=court,
        date_filed=date_filed,
        parsed_citations=cites,
        judges=get_judges(soup),
        precedential_status=get_precedential_status(soup, cites),
        page_count=get_page_count(soup),
        body_characters=clean_body_content(
            str(soup.select_one("casebody") or ""), harvard_file=True
        ),
        cluster_fields=cluster_fields,
        opinions=opinions,
    )


def find_imported_scan(scan_case: ScanCase) -> OpinionCluster | None:
    """Find the cluster this scanned opinion was already imported into.

    The stored XML file name starts with the scan and opinion ids, so it is
    looked for in the clusters with one of the opinion's citations, which
    are indexed, unlike the file path.

    Caveat: a merged cluster that didn't get any of the scan's citations
    isn't found here; `find_existing_cluster` matches it again, and the
    import is skipped because the cluster already has a scan XML.

    :param scan_case: The parsed scanned opinion.
    :return: The cluster, or None if it was not imported yet.
    """
    citations = Q()
    for cite in scan_case.parsed_citations:
        citations |= Q(
            citations__volume=cite.groups["volume"],
            citations__reporter=cite.corrected_reporter(),
            citations__page=cite.groups["page"],
        )
    return (
        OpinionCluster.objects.filter(
            citations,
            filepath_xml_scan__contains=f"/{scan_case.file_name_prefix}",
        )
        .distinct()
        .first()
    )


def find_existing_cluster(scan_case: ScanCase) -> OpinionCluster | None:
    """Find a cluster from another source that matches the scanned opinion.

    Uses the Harvard importer's matching: first by citation, then by court
    and date, comparing case names, docket numbers and opinion text.

    :param scan_case: The parsed scanned opinion.
    :return: The matching cluster, or None.
    """
    # `find_previously_imported_cases` expects Harvard-shaped data
    data = {
        "citations": [{"cite": cite} for cite in scan_case.citations],
        "docket_number": scan_case.docket_number,
        "name_abbreviation": scan_case.case_name,
    }
    return find_previously_imported_cases(
        data,
        scan_case.court.pk,
        scan_case.date_filed,
        scan_case.body_characters,
        scan_case.case_name_full,
        scan_case.citation,
    )


def make_opinion(op: Tag, cluster_id: int) -> Opinion:
    """Build an unsaved Opinion from an `<opinion>` element.

    :param op: The opinion element.
    :param cluster_id: The id of the cluster the opinion belongs to.
    :return: The unsaved Opinion.
    """
    opinion_xml = str(op)
    author_str = ""
    per_curiam = False
    if author := op.select_one("author"):
        for page_number in author.select("page-number"):
            page_number.extract()
        author_text = author.get_text(" ", strip=True)
        # Check the raw text: extract_judge_last_name drops "Per Curiam"
        per_curiam = bool(PER_CURIAM_RE.search(author_text))
        # A byline can name several judges ("Klein and Stone, JJ.")
        author_str = titlecase(
            ", ".join(
                extract_judge_last_name(titlecase(author_text.strip(":")))
            )
        )
    op_type = op.get("type")
    return Opinion(
        cluster_id=cluster_id,
        type=map_opinion_type(op_type if isinstance(op_type, str) else ""),
        author_str="Per Curiam" if per_curiam else author_str,
        per_curiam=per_curiam,
        xml_scan=opinion_xml,
        extracted_by_ocr=True,
    )


def link_judges(cluster: OpinionCluster, opinions: list[Opinion]) -> None:
    """Link the judges named in the scan to people in the judges database.

    Like the scrapers do, an opinion's author comes from its `author_str`,
    or from the cluster's `judges` when the cluster has a single opinion
    without an author. When `judges` names several people, they are added
    to the cluster's panel. Call it after the cluster is saved and before
    the opinions are.

    Caveat: a name that matches more than one person is left unresolved.

    :param cluster: The saved cluster.
    :param opinions: The cluster's unsaved opinions.
    :return: None
    """
    court_id = cluster.docket.court_id
    if cluster.judges:
        candidates = async_to_sync(lookup_judges_by_messy_str)(
            cluster.judges, court_id, cluster.date_filed
        )
        if (
            len(candidates) == 1
            and len(opinions) == 1
            and not opinions[0].author_str
        ):
            opinions[0].author = candidates[0]
        elif len(candidates) > 1:
            cluster.panel.add(*candidates)

    for opinion in opinions:
        if not opinion.author_str or opinion.per_curiam:
            continue
        candidates = async_to_sync(lookup_judges_by_messy_str)(
            opinion.author_str, court_id, cluster.date_filed
        )
        if len(candidates) == 1:
            opinion.author = candidates[0]


def store_scan_xml(
    cluster: OpinionCluster,
    scan_case: ScanCase,
    update_fields: list[str],
) -> None:
    """Upload the scanned XML to the cluster's `filepath_xml_scan` and save.

    Call it as the last step of the import transaction, so a failed database
    write rolls back before the file is uploaded. The upload comes before the
    cluster save that stores its path, so the file is deleted if that save
    fails, and no orphan is left.

    :param cluster: A cluster with a pk.
    :param scan_case: The parsed scanned opinion.
    :param update_fields: The other cluster fields to save with the path.
    :return: None
    """
    cluster.filepath_xml_scan.save(
        scan_case.file_name,
        ContentFile(scan_case.xml.encode()),
        save=False,
    )
    try:
        cluster.save(update_fields=["filepath_xml_scan", *update_fields])
    except Exception:
        cluster.filepath_xml_scan.delete(save=False)
        raise


def add_opinion_content(
    opinion: Opinion, scan_case: ScanCase
) -> OpinionContent:
    """Store the opinion XML in OpinionContent as the main version.

    The scan is richer than text from other sources, like scraped HTML, so
    it replaces the opinion's previous main version. The XML is also kept in
    `Opinion.xml_scan` until the site reads from OpinionContent.

    :param opinion: The saved opinion.
    :param scan_case: The parsed scanned opinion.
    :return: The new OpinionContent.
    """
    opinion.contents.filter(is_main_version=True).update(is_main_version=False)
    return OpinionContent.objects.create(
        opinion=opinion,
        content=opinion.xml_scan,
        source=OpinionContent.FLP_SCANNING,
        extraction_type=OpinionContent.OCR,
        is_main_version=True,
        sha1=sha1(opinion.xml_scan),
        page_count=scan_case.page_count,
    )


def merge_into_cluster(cluster: OpinionCluster, scan_case: ScanCase) -> None:
    """Merge a scanned opinion into an existing cluster.

    Adds missing citations, fills empty cluster fields, stores the XML,
    and updates the cluster and docket sources. The opinion text is only
    stored when both the cluster and the XML have a single opinion, since
    there is no reliable way yet to pair up multiple opinions.

    :param cluster: The matching cluster.
    :param scan_case: The parsed scanned opinion.
    :return: None
    """
    with transaction.atomic():
        add_citations_to_cluster(scan_case.citations, cluster.id)

        # Only save the changed fields, since the cluster was loaded before
        # the slow matching and other processes may have changed it since
        update_fields = ["source", "date_modified"]
        for field_name, value in {
            **scan_case.cluster_fields,
            "judges": scan_case.judges,
        }.items():
            if not value:
                continue
            if current := getattr(cluster, field_name):
                if current != value:
                    logger.debug(
                        "Cluster %s keeps its %s %r instead of the scan's %r",
                        cluster.id,
                        field_name,
                        current,
                        value,
                    )
                continue
            logger.info(
                "Filling empty %s of cluster %s", field_name, cluster.id
            )
            setattr(cluster, field_name, value)
            update_fields.append(field_name)
        if cluster.precedential_status in ("", PRECEDENTIAL_STATUS.UNKNOWN):
            cluster.precedential_status = scan_case.precedential_status
            update_fields.append("precedential_status")
        cluster.source = ClusterSources.merge_sources(
            cluster.source, ClusterSources.SCANNING_PROJECT
        )

        docket = cluster.docket
        docket.source = Docket.merge_sources(
            docket.source, Docket.SCANNING_PROJECT
        )
        docket.save(update_fields=["source"])

        # Versions of an opinion are kept in its cluster; skip them
        cl_opinions = list(
            cluster.sub_opinions.filter(main_version__isnull=True)
        )
        if len(cl_opinions) == 1 and len(scan_case.opinions) == 1:
            opinion = cl_opinions[0]
            opinion.xml_scan = str(scan_case.opinions[0])
            opinion.save(update_fields=["xml_scan"])
            add_opinion_content(opinion, scan_case)
        else:
            logger.warning(
                "Cluster %s has %s opinions and the scan of %s has %s. "
                "Opinion content was not merged.",
                cluster.id,
                len(cl_opinions),
                scan_case.citation.corrected_citation(),
                len(scan_case.opinions),
            )

        # Saves the cluster changes above too
        store_scan_xml(cluster, scan_case, update_fields)


def add_new_case(scan_case: ScanCase) -> OpinionCluster:
    """Create the docket, cluster, citations and opinions of a scanned case.

    :param scan_case: The parsed scanned opinion.
    :return: The new cluster.
    """
    with transaction.atomic():
        docket = update_or_create_docket(
            scan_case.case_name,
            scan_case.case_name_short,
            scan_case.court,
            scan_case.docket_number,
            Docket.SCANNING_PROJECT,
            from_harvard=False,
            case_name_full=scan_case.case_name_full,
            ia_needs_upload=False,
        )
        if docket.pk and case_names_are_too_different(
            docket.case_name, scan_case.case_name
        ):
            # Old reporters reuse short docket numbers like "No. 12", so a
            # docket found by number alone can be an unrelated case
            logger.info(
                "Docket %s has the docket number of %s but is a different "
                "case. Creating a new docket.",
                docket.pk,
                scan_case.citation.corrected_citation(),
            )
            docket = Docket(
                case_name=scan_case.case_name,
                case_name_short=scan_case.case_name_short,
                case_name_full=scan_case.case_name_full,
                source=Docket.SCANNING_PROJECT,
                docket_number=scan_case.docket_number,
                docket_number_raw=scan_case.docket_number,
                court=scan_case.court,
                ia_needs_upload=False,
            )
        elif docket.pk:
            logger.info("Using existing docket %s", docket.pk)
        docket.save()

        cluster = OpinionCluster(
            docket=docket,
            case_name=scan_case.case_name,
            case_name_short=scan_case.case_name_short,
            case_name_full=scan_case.case_name_full,
            precedential_status=scan_case.precedential_status,
            source=ClusterSources.SCANNING_PROJECT,
            date_filed=scan_case.date_filed,
            judges=scan_case.judges,
            **scan_case.cluster_fields,
        )
        cluster.save()
        add_citations_to_cluster(scan_case.citations, cluster.id)
        opinions = [make_opinion(op, cluster.id) for op in scan_case.opinions]
        link_judges(cluster, opinions)
        for opinion in opinions:
            opinion.save()
            add_opinion_content(opinion, scan_case)
        store_scan_xml(cluster, scan_case, update_fields=[])
    return cluster


def import_scanned_opinion(
    xml: str, file_path: str, court_id: str | None, dry_run: bool = False
) -> None:
    """Import a scanning project final XML into CourtListener.

    Skips opinions already imported from the scanning project. Merges into
    a matching cluster from another source when one exists; otherwise
    creates a new docket, cluster, citations and opinions.

    :param xml: The XML content.
    :param file_path: The local path or the S3 key of the XML, used for
        logging.
    :param court_id: The CL court id, or None to look it up in the XML.
    :param dry_run: Only log whether the opinion would be skipped, merged or
        added, without writing to the database or uploading files.
    :return: None
    """
    logger.info("Processing %s", file_path)
    if not (scan_case := parse_scan_xml(xml, file_path, court_id)):
        return
    citation = scan_case.citation.corrected_citation()

    if cluster := find_imported_scan(scan_case):
        logger.info(
            "Skipping %s (%s), already imported in cluster %s",
            file_path,
            citation,
            cluster.id,
        )
        return

    if cluster := find_existing_cluster(scan_case):
        if cluster.filepath_xml_scan:
            # Two scanned opinions matched the same cluster; needs review
            logger.warning(
                "%s (%s) matched cluster %s, which already has scan XML %s",
                file_path,
                citation,
                cluster.id,
                cluster.filepath_xml_scan.name,
            )
            return
        if dry_run:
            logger.info(
                "Dry run: would merge %s (%s) into cluster %s: %s%s",
                file_path,
                citation,
                cluster.id,
                BASE_URL,
                cluster.get_absolute_url(),
            )
            return
        logger.info(
            "Merging %s (%s) into cluster %s: %s%s",
            file_path,
            citation,
            cluster.id,
            BASE_URL,
            cluster.get_absolute_url(),
        )
        merge_into_cluster(cluster, scan_case)
        return

    if dry_run:
        logger.info(
            "Dry run: would add %s (%s) as a new cluster",
            scan_case.case_name,
            citation,
        )
        return
    cluster = add_new_case(scan_case)
    logger.info(
        "Added %s (%s) as cluster %s: %s%s",
        scan_case.case_name,
        citation,
        cluster.id,
        BASE_URL,
        cluster.get_absolute_url(),
    )


class Command(VerboseCommand):
    """Import scanning project final XML files into CourtListener."""

    help = (
        "Import opinions from the scanning project final XML files, merging "
        "them into existing clusters when possible."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the command arguments.

        :param parser: The command parser.
        :return: None
        """
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--path",
            type=str,
            help="An XML file, or a directory searched recursively for XML "
            "files.",
        )
        source.add_argument(
            "--scan-id",
            nargs="+",
            type=str,
            help="Import the XML files of these scans from the scanning "
            "portal's bucket.",
        )
        source.add_argument(
            "--all",
            action="store_true",
            help="Import every XML file in the scanning portal's bucket.",
        )
        parser.add_argument(
            "--opinion-id",
            type=str,
            help="Import a single opinion of the scan given in --scan-id.",
        )
        parser.add_argument(
            "--court-id",
            type=str,
            help="The CL court id. If not given, it is looked up from the "
            "court element of each XML.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log what would be skipped, merged or added without "
            "changing anything.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Import every XML file found in the given path.

        :return: None
        """
        super().handle(*args, **options)
        scan_ids, opinion_id = options["scan_id"], options["opinion_id"]
        if opinion_id and (not scan_ids or len(scan_ids) != 1):
            raise CommandError("--opinion-id needs a single --scan-id.")

        if options["path"]:
            file_paths = xml_file_paths(options["path"])
            read = read_local_xml
        else:
            storage = ScanningFinalXmlStorage()
            file_paths = s3_xml_keys(storage, scan_ids, opinion_id)
            read = partial(read_s3_xml, storage)
        logger.info("Found %s XML files to import", len(file_paths))

        for file_path in file_paths:
            try:
                import_scanned_opinion(
                    read(file_path),
                    file_path,
                    options["court_id"],
                    options["dry_run"],
                )
            except Exception:
                # Keep going; one bad file shouldn't stop a volume import
                logger.exception("Failed to import %s", file_path)

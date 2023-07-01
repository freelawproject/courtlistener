import calendar
import re
import string
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup
from courts_db import find_court_by_id
from django.conf import settings
from django.db import transaction
from eyecite import clean_text
from eyecite.find import get_citations
from juriscraper.lib.string_utils import titlecase

from cl.search.models import (
    SOURCES,
    Citation,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
)

from ...citations.utils import map_reporter_db_cite_type
from ...lib.command_utils import logger
from ...people_db.lookup_utils import (
    lookup_judge_by_last_name,
    lookup_judges_by_last_name_list,
)
from ..management.commands.harvard_opinions import (
    clean_body_content,
    match_based_text,
)

# used to identify dates
# the order of these dates matters, as if there are multiple matches in an
# opinion for one type of date tag, the date associated to the --last-- matched
# tag will be the ones used for that type of date
FILED_TAGS = [
    "filed",
    "opinion filed",
    "date",
    "order filed",
    "delivered and filed",
    "letter filed",
    "dated",
    "release date",
    "filing date",
    "filed date",
    "date submitted",
    "as of",
    "opinions filed",
    "filed on",
    "decision filed",
]
DECIDED_TAGS = ["decided", "date decided", "decided on", "decided date"]
ARGUED_TAGS = [
    "argued",
    "submitted",
    "submitted on briefs",
    "on briefs",
    "heard",
    "considered on briefs",
    "argued and submitted",
    "opinion",
    "opinions delivered",
    "opinion delivered",
    "assigned on briefs",
    "opinion issued",
    "delivered",
    "rendered",
    "considered on briefs on",
    "opinion delivered and filed",
    "orally argued",
    "rendered on",
    "oral argument",
    "submitted on record and briefs",
]
REARGUE_DENIED_TAGS = [
    "reargument denied",
    "rehearing denied",
    "further rehearing denied",
    "as modified on denial of rehearing",
    "order denying rehearing",
    "petition for rehearing filed",
    "motion for rehearing filed",
    "rehearing denied to bar commission",
    "reconsideration denied",
    "denied",
    "review denied",
    "motion for rehearing and/or transfer to supreme court denied",
    "motion for reargument denied",
    "petition and crosspetition for review denied",
    "opinion modified and as modified rehearing denied",
    "motion for rehearing andor transfer to supreme court denied",
    "petition for rehearing denied",
    "leave to appeal denied",
    "rehearings denied",
    "motion for rehearing denied",
    "second rehearing denied",
    "petition for review denied",
    "appeal dismissed",
    "rehearing en banc denied",
    "rehearing and rehearing en banc denied",
    "order denying petition for rehearing",
    "all petitions for review denied",
    "petition for allowance of appeal denied",
    "opinion modified and rehearing denied",
    "as amended on denial of rehearing",
    "reh denied",
]
REARGUE_TAGS = ["reargued", "reheard", "upon rehearing", "on rehearing"]
CERT_GRANTED_TAGS = [
    "certiorari granted",
    "petition and crosspetition for writ of certiorari granted",
]
CERT_DENIED_TAGS = [
    "certiorari denied",
    "certiorari quashed",
    "certiorari denied by supreme court",
    "petition for certiorari denied by supreme court",
]
UNKNOWN_TAGS = [
    "petition for review allowed",
    "affirmed",
    "reversed and remanded",
    "rehearing overruled",
    "review granted",
    "decision released",
    "transfer denied",
    "released for publication",
    "application to transfer denied",
    "amended",
    "reversed",
    "opinion on petition to rehear",
    "suggestion of error overruled",
    "cv",
    "case stored in record room",
    "met to file petition for review disposed granted",
    "rehearing granted",
    "opinion released",
    "permission to appeal denied by supreme court",
    "rehearing pending",
    "application for transfer denied",
    "effective date",
    "modified",
    "opinion modified",
    "transfer granted",
    "discretionary review denied",
    "application for leave to file second petition for rehearing denied",
    "final",
    "date of judgment entry on appeal",
    "petition for review pending",
    "writ denied",
    "rehearing filed",
    "as extended",
    "officially released",
    "appendix filed",
    "spring sessions",
    "summer sessions",
    "fall sessions",
    "winter sessions",
    "discretionary review denied by supreme court",
    "dissenting opinion",
    "en banc reconsideration denied",
    "answer returned",
    "refiled",
    "revised",
    "modified upon denial of rehearing",
    "session mailed",
    "reversed and remanded with instructions",
    "writ granted",
    "date of judgment entry",
    "preliminary ruling rendered",
    "amended on",
    "dissenting opinion filed",
    "concurring opinion filed",
    "memorandum dated",
    "mandamus denied on mandate",
    "updated",
    "date of judgment entered",
    "released and journalized",
    "submitted on",
    "case assigned",
    "opinion circulated for comment",
    "submitted on rehearing",
    "united states supreme court dismissed appeal",
    "answered",
    "reconsideration granted in part and as amended",
    "as amended on denial of rehearing",
    "reassigned",
    "as amended",
    "as corrected",
    "writ allowed",
    "released",
    "application for leave to appeal filed",
    "affirmed on appeal reversed and remanded",
    "as corrected",
    "withdrawn substituted and refiled",
    "answered",
    "released",
    "as modified and ordered published",
    "remanded",
    "concurring opinion added",
    "decision and journal entry dated",
    "memorandum filed",
    "as modified",
]

# used to check if a docket number appears in what should be a citation string
# the order matters, as these are stripped from a docket string in order
DOCKET_JUNK = [
    "c.a. no. kc",
    "c.a. no. pm",
    "c.a. no.",
    "i.c. no.",
    "case no.",
    "no.",
]

# known abbreviations that indicate if a citation isn't actually a citation
BAD_CITES = ["Iowa App.", "R.I.Super.", "Ma.Super.", "Minn.App.", "NCIC"]

# used to figure out if a "citation text" is really a citation
TRIVIAL_CITE_WORDS = (
    [n.lower() for n in calendar.month_name]
    + [n.lower()[:3] for n in calendar.month_name]
    + ["no"]
)

# used to map the parsed opinion types to their tags in the populated opinion
# objects
OPINION_TYPE_MAPPING = {
    "opinion": Opinion.LEAD,
    "dissent": Opinion.DISSENT,
    "concurrence": Opinion.CONCUR_IN_PART,
}


def convert_columbia_html(text: str) -> str:
    """Convert xml tags to html tags
    :param text: Text to convert to html
    :return: converted text
    """

    conversions = [
        ("italic", "em"),
        ("block_quote", "blockquote"),
        ("bold", "strong"),
        ("underline", "u"),
        ("strikethrough", "strike"),
        ("superscript", "sup"),
        ("subscript", "sub"),
        ("heading", "h3"),
        ("table", "pre"),
    ]

    for pattern, replacement in conversions:
        text = re.sub(f"<{pattern}>", f"<{replacement}>", text)
        text = re.sub(f"</{pattern}>", f"</{replacement}>", text)

    # grayed-out page numbers
    text = re.sub("<page_number>", ' <span class="star-pagination">*', text)
    text = re.sub("</page_number>", "</span> ", text)

    # footnotes
    foot_references = re.findall(
        "<footnote_reference>.*?</footnote_reference>", text
    )

    for ref in foot_references:
        try:
            fnum = re.search(r"[\*\d]+", ref).group()
        except AttributeError:
            fnum = re.search(r"\[fn(.+)\]", ref).group(1)
        rep = f'<sup id="ref-fn{fnum}"><a href="#fn{fnum}">{fnum}</a></sup>'
        text = text.replace(ref, rep)

    # Add footnotes to opinion
    footnotes = re.findall("<footnote_body>.[\s\S]*?</footnote_body>", text)
    for fn in footnotes:
        content = re.search("<footnote_body>(.[\s\S]*?)</footnote_body>", fn)
        rep = r'<div class="footnote">%s</div>' % content.group(1)
        text = text.replace(fn, rep)

    # Replace footnote numbers
    foot_numbers = re.findall("<footnote_number>.*?</footnote_number>", text)
    for ref in foot_numbers:
        try:
            fnum = re.search(r"[\*\d]+", ref).group()
        except:
            fnum = re.search(r"\[fn(.+)\]", ref).group(1)
        rep = r'<sup id="fn%s"><a href="#ref-fn%s">%s</a></sup>' % (
            fnum,
            fnum,
            fnum,
        )
        text = text.replace(ref, rep)

    # Make nice paragraphs. This replaces double newlines with paragraphs, then
    # nests paragraphs inside blockquotes, rather than vice versa. The former
    # looks good. The latter is bad.
    text = f"<p>{text}</p>"
    text = re.sub(r"</blockquote>\s*<blockquote>", "\n\n", text)
    text = re.sub("\n\n", "</p>\n<p>", text)
    text = re.sub(r"<p>\s*<blockquote>", "<blockquote><p>", text, re.M)
    text = re.sub("</blockquote></p>", "</p></blockquote>", text, re.M)

    return text


def add_new_case(
    item: dict,
    skip_dupes: bool = False,
    min_dates: bool = None,
    start_dates: Optional[dict] = None,
    testing: bool = True,
):
    """Associates case data from `parse_opinions` with objects. Saves these
    objects.
    item: dict containing case data
    skip_dupes: if set, will skip duplicates.
    min_dates: if not none, will skip cases after min_dates
    start_dates: if set, will throw exception for cases before court was
    founded.
    testing: don't save the data if true
    """
    date_filed = (
        date_argued
    ) = (
        date_reargued
    ) = date_reargument_denied = date_cert_granted = date_cert_denied = None
    unknown_date = None
    current_year = date.today().year
    for date_cluster in item["dates"]:
        for date_info in date_cluster:
            # check for any dates that clearly aren't dates
            if date_info[1].year < 1600 or date_info[1].year > current_year:
                continue
            # check for untagged dates that will be assigned to date_filed
            if date_info[0] is None:
                date_filed = date_info[1]
                continue
            # try to figure out what type of date it is based on its tag string
            if date_info[0] in FILED_TAGS:
                date_filed = date_info[1]
            elif date_info[0] in DECIDED_TAGS:
                if not date_filed:
                    date_filed = date_info[1]
            elif date_info[0] in ARGUED_TAGS:
                date_argued = date_info[1]
            elif date_info[0] in REARGUE_TAGS:
                date_reargued = date_info[1]
            elif date_info[0] in REARGUE_DENIED_TAGS:
                date_reargument_denied = date_info[1]
            elif date_info[0] in CERT_GRANTED_TAGS:
                date_cert_granted = date_info[1]
            elif date_info[0] in CERT_DENIED_TAGS:
                date_cert_denied = date_info[1]
            else:
                unknown_date = date_info[1]
                if date_info[0] not in UNKNOWN_TAGS:
                    logger.info(
                        f"Found unknown date tag {date_info[0]} with date {date_info[1]} in file {item['file']}.xml"
                    )

    # the main date (used for date_filed in OpinionCluster) and panel dates
    # (used for finding judges) are ordered in terms of which type of dates
    # best reflect them
    main_date = (
        date_filed
        or date_argued
        or date_reargued
        or date_reargument_denied
        or unknown_date
    )
    panel_date = (
        date_argued
        or date_reargued
        or date_reargument_denied
        or date_filed
        or unknown_date
    )

    if main_date is None:
        raise Exception(f"Failed to get a date for {item['file']}")

    if not Court.objects.filter(id=item["court_id"]).exists():
        raise Exception(
            f"Court doesn't exist in CourtListener with id: {item['court_id']}"
        )

    # special rule for Kentucky
    if item["court_id"] == "kycourtapp" and main_date <= date(1975, 12, 31):
        item["court_id"] = "kycourtapphigh"

    if min_dates is not None:
        if min_dates.get(item["court_id"]) is not None:
            if main_date >= min_dates[item["court_id"]]:
                logger.info(
                    f"{main_date} after {min_dates[item['court_id']]} -- skipping."
                )
                return
    if start_dates is not None:
        if start_dates.get(item["court_id"]) is not None:
            if main_date <= start_dates[item["court_id"]]:
                logger.info(
                    f"{main_date} before court founding: {start_dates[item['court_id']]} -- skipping."
                )
                return

    docket = Docket(
        source=Docket.COLUMBIA,
        date_argued=date_argued,
        date_reargued=date_reargued,
        date_cert_granted=date_cert_granted,
        date_cert_denied=date_cert_denied,
        date_reargument_denied=date_reargument_denied,
        court_id=item["court_id"],
        case_name_short=item["case_name_short"] or "",
        case_name=item["case_name"] or "",
        case_name_full=item["case_name_full"] or "",
        docket_number=item["docket"] or "",
    )

    # get citation objects in a list for addition to the cluster
    found_citations = []
    for c in item["citations"]:
        found = get_citations(clean_text(c, ["html", "inline_whitespace"]))
        if not found:
            # if the docket number --is-- citation string, we're likely dealing
            # with a somewhat common triplet of (docket number, date,
            # jurisdiction), which isn't a citation at all (so there's no
            # problem)
            if item["docket"]:
                docket_no = item["docket"].lower()
                if "claim no." in docket_no:
                    docket_no = docket_no.split("claim no.")[0]
                for junk in DOCKET_JUNK:
                    docket_no = docket_no.replace(junk, "")
                docket_no = docket_no.strip(".").strip()
                if docket_no and docket_no in c.lower():
                    continue

            # there are a trivial number of letters (except for
            # months and a few trivial words) in the citation,
            # then it's not a citation at all
            non_trivial = c.lower()
            for trivial in TRIVIAL_CITE_WORDS:
                non_trivial = non_trivial.replace(trivial, "")
            num_letters = sum(
                non_trivial.count(letter) for letter in string.ascii_lowercase
            )
            if num_letters < 3:
                continue

            # if there is a string that's known to indicate
            # a bad citation, then it's not a citation
            if any(bad in c for bad in BAD_CITES):
                continue
            # otherwise, this is a problem
            raise Exception(
                "Failed to get a citation from the string '%s' in "
                "court '%s' with docket '%s'."
                % (c, item["court_id"], item["docket"])
            )
        else:
            if found:
                if not found[0].corrected_reporter():
                    reporter_type = Citation.STATE
                else:
                    cite_type_str = found[0].all_editions[0].reporter.cite_type
                    reporter_type = map_reporter_db_cite_type(cite_type_str)

                citation_object = Citation(
                    volume=found[0].groups["volume"],
                    reporter=found[0].corrected_reporter(),
                    page=found[0].groups["page"],
                    type=reporter_type,
                )
                found_citations.append(citation_object)

    cluster = OpinionCluster(
        judges=item.get("judges", "") or "",
        precedential_status=(
            "Unpublished" if item["unpublished"] else "Published"
        ),
        date_filed=main_date,
        case_name_short=item["case_name_short"] or "",
        case_name=item["case_name"] or "",
        case_name_full=item["case_name_full"] or "",
        source=SOURCES.COLUMBIA_ARCHIVE,
        attorneys=item["attorneys"] or "",
        posture=item["posture"] or "",
    )
    panel = lookup_judges_by_last_name_list(
        item["panel"], item["court_id"], panel_date
    )

    opinions = []
    for i, opinion_info in enumerate(item["opinions"]):
        if opinion_info["author"] is None:
            author = None
            author_str = ""
        else:
            author = lookup_judge_by_last_name(
                opinion_info["author"], item["court_id"], panel_date
            )
            author_str = opinion_info["author"]

        footnotes = ""
        if opinion_info["footnotes"]:
            footnotes = (
                f'<div class="footnotes">{opinion_info["footnotes"]}</div>'
            )

        converted_text = convert_columbia_html(
            opinion_info["opinion"] + footnotes
        )
        opinion_type = OPINION_TYPE_MAPPING[opinion_info["type"]]
        if opinion_type == Opinion.LEAD and i > 0:
            opinion_type = Opinion.ADDENDUM

        # TODO add order field when changes get merged in main
        # TODO local_path save file, not only path?
        opinion = Opinion(
            author=author,
            author_str=titlecase(author_str),
            per_curiam=opinion_info["per_curiam"],
            type=opinion_type,
            # type=OPINION_TYPE_MAPPING[opinion_info['type']],
            html_columbia=converted_text,
            sha1=opinion_info["sha1"],
            # This is surely not updated for the new S3 world. If you're
            # reading this, you'll need to update this code.
            local_path=opinion_info["local_path"],
        )

        joined_by = lookup_judges_by_last_name_list(
            item.get("joining", ""), item.get("court_id", ""), panel_date
        )

        opinions.append((opinion, joined_by))

    if min_dates is None:
        # check to see if this is a duplicate
        previously_imported_case = find_duplicates(
            docket, cluster, opinions, found_citations
        )
        if previously_imported_case:
            if skip_dupes:
                logger.info(
                    f"Duplicate data found for file: {item['file']}. Skipping."
                )
            else:
                raise Exception(f"Found duplicate(s).")

    # save all the objects
    if not testing:
        with transaction.atomic():
            docket.save()
            cluster.docket = docket
            cluster.save(index=False)
            for citation in found_citations:
                citation.cluster = cluster
                citation.save()
            for member in panel:
                cluster.panel.add(member)
            for opinion, joined_by in opinions:
                opinion.cluster = cluster
                opinion.save(index=False)
                for joiner in joined_by:
                    opinion.joined_by.add(joiner)
            if settings.DEBUG:
                domain = "http://127.0.0.1:8000"
            else:
                domain = "https://www.courtlistener.com"
            logger.info(
                f"Created item at: {domain}{cluster.get_absolute_url()}"
            )


def find_duplicates(
    docket, cluster, opinions, citation_list
) -> Optional[OpinionCluster]:
    """Check if there is a duplicate cluster using the unsaved objects data
    :param docket: docket to be created
    :param cluster: cluster to be created
    :param opinions: list of opinions to be created
    :param citation_list: list of citations to be created
    :return: cluster match or None
    """
    for citation in citation_list:
        cites = get_citations(str(citation))

        if cites:
            xml_opinions_content = []
            for op in opinions:
                xml_opinions_content.append(op[0].html_columbia)

            all_opinions_content = " ".join(xml_opinions_content)
            all_opinions_soup = BeautifulSoup(
                all_opinions_content, features="html.parser"
            )
            possible_clusters = OpinionCluster.objects.filter(
                citations__reporter=citation.reporter,
                citations__volume=citation.volume,
                citations__page=citation.page,
            ).order_by("id")

            match = match_based_text(
                clean_body_content(all_opinions_soup.text),
                docket.docket_number,
                cluster.case_name,
                possible_clusters,
                cluster.case_name_short,
                cites[0],
            )

            if match:
                return match

    return None

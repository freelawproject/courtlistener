import calendar
import re
import string
from collections import OrderedDict
from datetime import date

from django.conf import settings
from eyecite.find import get_citations
from eyecite.utils import clean_text

from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.solr_core_admin import get_term_frequency
from cl.search.models import SOURCES, Docket, Opinion, OpinionCluster

from ...people_db.lookup_utils import (
    lookup_judge_by_last_name,
    lookup_judges_by_last_name_list,
)
from .convert_columbia_html import convert_columbia_html

# only make a solr connection once
SOLR_CONN = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode="r")


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


def make_and_save(
    item, skipdupes=False, min_dates=None, start_dates=None, testing=True
):
    """Associates case data from `parse_opinions` with objects. Saves these
    objects.

    min_date: if not none, will skip cases after min_date
    """
    date_filed = (
        date_argued
    ) = (
        date_reargued
    ) = date_reargument_denied = date_cert_granted = date_cert_denied = None
    unknown_date = None
    for date_cluster in item["dates"]:
        for date_info in date_cluster:
            # check for any dates that clearly aren't dates
            if date_info[1].year < 1600 or date_info[1].year > 2020:
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
                    print(
                        "\nFound unknown date tag '%s' with date '%s'.\n"
                        % date_info
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

    # special rule for Kentucky
    if item["court_id"] == "kycourtapp" and main_date <= date(1975, 12, 31):
        item["court_id"] = "kycourtapphigh"

    if min_dates is not None:
        if min_dates.get(item["court_id"]) is not None:
            if main_date >= min_dates[item["court_id"]]:
                print(
                    main_date,
                    "after",
                    min_dates[item["court_id"]],
                    " -- skipping.",
                )
                return
    if start_dates is not None:
        if start_dates.get(item["court_id"]) is not None:
            if main_date <= start_dates[item["court_id"]]:
                print(
                    main_date,
                    "before court founding:",
                    start_dates[item["court_id"]],
                    " -- skipping.",
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
                non_trivial.count(letter) for letter in string.lowercase
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
            found_citations.extend(found.to_model())

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
        else:
            author = lookup_judge_by_last_name(
                opinion_info["author"], item["court_id"], panel_date
            )

        converted_text = convert_columbia_html(opinion_info["opinion"])
        opinion_type = OPINION_TYPE_MAPPING[opinion_info["type"]]
        if opinion_type == Opinion.LEAD and i > 0:
            opinion_type = Opinion.ADDENDUM

        opinion = Opinion(
            author=author,
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
            item["joining"], item["court_id"], panel_date
        )
        opinions.append((opinion, joined_by))

    if min_dates is None:
        # check to see if this is a duplicate
        dups = find_dups(docket, cluster)
        if dups:
            if skipdupes:
                print("Duplicate. skipping.")
            else:
                raise Exception(f"Found {len(dups)} duplicate(s).")

    # save all the objects
    if not testing:
        try:
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
            print(f"Created item at: {domain}{cluster.get_absolute_url()}")
        except:
            # if anything goes wrong, try to delete everything
            try:
                docket.delete()
            except:
                pass
            raise


def find_dups(docket, cluster):
    """Finds the duplicate cases associated to a collection of objects.

    :param docket: A `Docket` instance.
    :param cluster: An `OpinionCluster` instance.
    """
    if not cluster.citations.exists():
        # if there aren't any citations, assume
        # for now that there's no duplicate
        return []

    params = {
        "fq": [
            f"court_id:{docket.court_id}",
            "citation:(%s)"
            % " OR ".join('"%s"~5' % c for c in cluster.citations.all() if c),
        ],
        "rows": 100,
        "caller": "corpus_importer.import_columbia.populate_opinions",
    }
    results = SOLR_CONN.query().add_extra(**params).execute()
    if len(results) == 1:
        # found the duplicate
        return results
    elif len(results) > 1:
        # narrow down the cases that match citations
        remaining = []
        base_words = get_case_name_words(docket.case_name)
        for r in results:
            # if the important words in case names don't match up, these aren't
            # duplicates
            if not r.get("caseName"):
                continue
            if get_case_name_words(r["caseName"]) == base_words:
                remaining.append(r)
        if remaining:
            # we successfully narrowed down the results
            return remaining
        # failed to narrow down results, so we just return the cases that match
        # citations
        return results
    return []


def get_case_name_words(case_name):
    """Gets all the important words in a case name. Returns them as a set."""
    case_name = case_name.lower()
    filtered_words = []
    all_words = case_name.split()
    if " v. " in case_name:
        v_index = all_words.index("v.")
        # The first word of the defendant and the last word in the plaintiff
        # that's not a bad word.
        plaintiff_a = get_good_words(all_words[:v_index])
        defendant_a = get_good_words(all_words[v_index + 1 :])
        if plaintiff_a:
            filtered_words.append(plaintiff_a[-1])
        if defendant_a:
            # append the first good word that's not already in the array
            try:
                filtered_words.append(
                    [
                        word
                        for word in defendant_a
                        if word not in filtered_words
                    ][0]
                )
            except IndexError:
                # When no good words left in defendant_a
                pass
    elif (
        "in re " in case_name
        or "matter of " in case_name
        or "ex parte" in case_name
    ):
        try:
            subject = re.search(
                "(?:(?:in re)|(?:matter of)|(?:ex parte)) (.*)", case_name
            ).group(1)
        except TypeError:
            subject = ""
        good_words = get_good_words(subject.split())
        if good_words:
            filtered_words.append(good_words[0])
    else:
        filtered_words = get_good_words(all_words)
    return set(filtered_words)


def get_good_words(word_list, stop_words_size=500):
    """Cleans out stop words, abbreviations, etc. from a list of words"""
    stopwords = StopWords().stop_words
    good_words = []
    for word in word_list:
        # Clean things up
        word = re.sub(r"'s", "", word)
        word = word.strip('*,();"')

        # Boolean conditions
        stop = word in stopwords[:stop_words_size]
        bad_stuff = re.search("[0-9./()!:&']", word)
        too_short = len(word) <= 1
        is_acronym = word.isupper() and len(word) <= 3
        if any([stop, bad_stuff, too_short, is_acronym]):
            continue
        else:
            good_words.append(word)
    # Eliminate dups, but keep order.
    return list(OrderedDict.fromkeys(good_words))


class StopWords(object):
    """A very simple object that can hold stopwords, but that is only
    initialized once.
    """

    stop_words = get_term_frequency(result_type="list")

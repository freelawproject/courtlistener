import itertools
import re
from collections import defaultdict
from difflib import Differ, SequenceMatcher
from typing import Union

from django.db import transaction
from django.db.models import Count, Q, QuerySet
from elasticsearch import NotFoundError
from eyecite import clean_text

from cl.alerts.models import DocketAlert
from cl.audio.models import Audio
from cl.favorites.models import DocketTag, Note
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.models import (
    AttorneyOrganizationAssociation,
    PartyType,
    Role,
)
from cl.recap.models import PacerFetchQueue, ProcessingQueue
from cl.scrapers.models import PACERMobilePageData
from cl.search.documents import ES_CHILD_ID, OpinionDocument
from cl.search.models import (
    SOURCES,
    BankruptcyInformation,
    Claim,
    Docket,
    DocketEntry,
    DocketPanel,
    DocketTags,
    Opinion,
    OpinionCluster,
    OpinionClusterNonParticipatingJudges,
    OpinionClusterPanel,
)

MIN_SEQUENCE_SIMILARITY = 0.9
DRY_RUN = False


def explain_version_differences(opinions: list[Opinion | int]) -> None:
    """Debugging function to inspect version differences

    :param opinions: a list of Opinion objects or ids
    :return None
    """
    if isinstance(opinions[0], int):
        opinions = [
            Opinion.objects.get(id=opinion_id) for opinion_id in opinions
        ]

    text_combinations = itertools.combinations(
        [(opinion.id, opinion.plain_text.strip()) for opinion in opinions], 2
    )
    for (op1, text1), (op2, text2) in text_combinations:
        if text1 == text2:
            print(f"Content is the same for {op1} {op2}")
            continue

        # Actually see the difference
        differ = Differ()
        prev_index = 0
        prev_key = ""
        diff = ""
        print(f"Difference between {op1} {op2}")
        for index, i in enumerate(differ.compare(text1, text2)):
            if i[0] in "-+?":
                if prev_index == index - 1 and prev_key == i[0]:
                    diff += i[-1]
                else:
                    print(
                        f"difference at index {index} is {prev_key} {repr(diff)}"
                    )
                    diff = ""
                prev_key = i[0]
                prev_index = index

        sm = SequenceMatcher(None, text1, text2)
        print("SequenceMatcher.ratio(text1, text2)", sm.ratio())
        sm = SequenceMatcher(None, text2, text1)
        print("SequenceMatcher.ratio(text2, text1)", sm.ratio())


models_that_reference_docket = [
    (DocketAlert, "docket"),
    (Audio, "docket"),
    (DocketTags, "docket"),
    (Note, "docket_id"),
    (AttorneyOrganizationAssociation, "docket"),
    (PartyType, "docket"),  # UNIQUE CONSTRAINT(docket_id, party_id, name)
    (
        Role,
        "docket",
    ),  # UNIQUE CONSTRAINT, btree (party_id, attorney_id, role, docket_id, date_action)
    (PacerFetchQueue, "docket"),
    (ProcessingQueue, "docket"),
    (PACERMobilePageData, "docket"),  # UNIQUE CONSTRAINT, btree (docket_id)
    (BankruptcyInformation, "docket"),  # UNIQUE CONSTRAINT, btree (docket_id)
    (Claim, "docket"),
    (DocketPanel, "docket"),  # UNIQUE CONSTRAINT, btree (docket_id, person_id)
    (DocketEntry, "docket"),
    (DocketTag, "docket"),  # UNIQUE CONSTRAINT, btree (docket_id, tag_id)
    (OpinionCluster, "docket"),
]

# related names are not standard
models_that_reference_cluster = [
    (Note, "cluster_id"),
    (Opinion, "cluster"),
    (OpinionClusterPanel, "opinioncluster"),
    (OpinionClusterNonParticipatingJudges, "opinioncluster"),
]


def get_separator(name: str) -> str:
    """Try to find a separator for a list of comma or colon separated names

    :param name: a judge name string
    :return: a separator string
    """
    for sep in ["; ", ";", ", ", ","]:
        if name.count(sep) > 1:
            return sep

    return ""


def merge_judge_names(name1: str, name2: str) -> str:
    """Merge 2 judge name strings while trying to reduce repetition in them

    If a string is contained in another, return the container.
    If they have something in common, merge them
    If there is nothing in common, concatenate them

    :param name1: a name
    :param name2: another name
    :return: a merged name
    """
    noise = {"judge", "justice", "j", "p", "chief"}

    # clean whitespace, commas, etc
    set1 = set(re.findall(r"\w+", name1.lower()))
    set2 = set(re.findall(r"\w+", name2.lower()))

    if not set1:
        return name2
    if not set2:
        return name1

    # `<=` is the subset operator
    if set1.difference(noise) <= set2:
        return name2
    if set2.difference(noise) <= set1:
        return name1

    if not set1.intersection(set2).difference(noise):
        # if they have nothing in common, just return the concatenation
        return f"{name1} {name2}"

    # if they have something in common, let's check if they are lists and try
    # to merge them
    sep1 = get_separator(name1)
    sep2 = get_separator(name2)
    if sep1 and sep2:
        parts1 = [p.strip() for p in name1.split(sep1)]
        parts2 = [p.strip() for p in name2.split(sep2)]
        merged_parts = []
        seen_parts = set()

        for part in parts1:
            if part.lower() not in seen_parts:
                merged_parts.append(part)
                seen_parts.add(part.lower())

        for part in parts2:
            if part.lower() not in seen_parts:
                merged_parts.append(part)
                seen_parts.add(part.lower())

        return "; ".join(merged_parts)

    # Fallback to concatenation if we couldn't merge them via separating lists
    # of names
    return f"{name1} {name2}"


docket_fields_to_merge = [
    ("source", Docket.merge_sources),
    "appeal_from",
    "parent_docket",
    "appeal_from_str",
    "originating_court_information",
    "idb_data",
    "assigned_to",
    "assigned_to_str",
    "referred_to",
    "referred_to_str",
    "panel_str",
    "date_last_index",
    "date_cert_granted",
    "date_cert_denied",
    "date_argued",
    "date_reargued",
    "date_reargument_denied",
    "date_filed",
    "date_terminated",
    "date_last_filing",
    "case_name_short",
    "case_name_full",
    "federal_dn_office_code",
    "federal_dn_case_type",
    "federal_dn_judge_initials_assigned",
    "federal_dn_judge_initials_referred",
    "federal_defendant_number",
    "pacer_case_id",
    "cause",
    "nature_of_suit",
    "jury_demand",
    "jurisdiction_type",
    "appellate_fee_status",
    "appellate_case_type_information",
    "mdl_status",
    "filepath_local",
    ("date_blocked", min),
    "blocked",
]

cluster_fields_to_merge = [
    ("judges", merge_judge_names),
    "date_filed",
    "date_filed_is_approximate",
    "case_name_short",
    "case_name_full",
    "scdb_id",
    "scdb_decision_direction",
    "scdb_votes_majority",
    "scdb_votes_minority",
    ("source", SOURCES.merge_sources),
    "procedural_history",
    "attorneys",
    "nature_of_suit",
    "posture",
    "syllabus",
    "blocked",
    ("date_blocked", min),
    "headnotes",
    "cross_reference",
    "correction",
    "disposition",
    "other_dates",
    "summary",
    "filepath_json_harvard",
    "filepath_pdf_harvard",
    "arguments",
    "headmatter",
]


def get_query_from_url(url: str, url_filter: str) -> Q:
    """Build an OR query with the alternative to http or https

    :param url: the input url
    :param url_filter: a string that identified a Django filter.
        Currently supporting
        - 'startswith'
        - 'exact', meaning an equality filter

    :return: a Q OR object
    """
    if url_filter not in ["exact", "startswith"]:
        raise ValueError("`url_filter` must be in [exact, startswith]")

    if "https" in url:
        extra_query = url.replace("https", "http")
    else:
        extra_query = url.replace("http", "https")

    if url_filter == "startswith":
        return Q(download_url__startswith=url) | Q(
            download_url__startswith=extra_query
        )

    return Q(download_url=url) | Q(download_url=extra_query)


def clean_opinion_text(opinion: Opinion) -> str:
    """Remove noise (HTML tags or extra whitespace) from an opinion's text

    :param opinion: the opinion
    :return: the cleaned text
    """
    if opinion.html:
        return clean_text(opinion.html, ["html", "all_whitespace"])

    return re.sub(r"\s+", " ", opinion.plain_text)


def text_is_similar(text1: str, text2: str) -> bool:
    """Check if the text from both opinions is the same or very similar

    :param text1: a cleaned opinion's text
    :param text2: another cleaned opinion's text
    """
    if text1 == text2:
        return True

    # a single character difference yields a 0.999 ratio
    # a single word difference may reduce the similarity a few points,
    # depending on how long the sequence is, and if it is an addition/removal
    # or a correction. In general, a 0.9 MIN value should tolerate a difference
    # of a few words between versions, which is what we expect
    # Note that this in sensible to argument order, so we retry with inverted
    # order if the first run fails
    sm = SequenceMatcher(None, text1, text2)
    ratio = sm.ratio()
    if ratio < MIN_SEQUENCE_SIMILARITY:
        return (
            SequenceMatcher(None, text2, text1).ratio()
            >= MIN_SEQUENCE_SIMILARITY
        )
    return ratio >= MIN_SEQUENCE_SIMILARITY


def update_referencing_objects(
    main_object: Union[OpinionCluster, Docket],
    version_object: Union[OpinionCluster, Docket],
):
    """Make all objects referencing to `version_object` point to `main_object`

    This way, prevent cascade deletion. Some of these may fail due to
    unique constraints; this will break the whole update. Let's let this
    happen so we can debug, and control it later

    :param main_object: the main version OpinionCluster or Docket
    :param version_object: the secondary version OpinionCluster or Docket
    """
    if isinstance(main_object, OpinionCluster):
        referencing_models = models_that_reference_cluster
    elif isinstance(main_object, Docket):
        referencing_models = models_that_reference_docket
    else:
        return

    for model, related_name in referencing_models:
        filter_query = {related_name: version_object}
        update_query = {related_name: main_object}

        qs = model.objects.filter(**filter_query)
        if qs.exists():
            logger.info(
                "Updating related %s for %s %s",
                model._meta.model_name,
                main_object._meta.model_name,
                main_object.id,
            )
            qs.update(**update_query)


def merge_metadata(
    main_object: Union[Opinion, OpinionCluster, Docket],
    version_object: Union[Opinion, OpinionCluster, Docket],
) -> bool:
    """Merge `fields_to_merge` from `version_object` into `main_object`

    :param main_object: the main OpinionCluster or Opinion or Docket
    :param version_object: the secondary version Opinion, or its OpinionCluster
    :return: True if the main object was updated and needs to be saved
    """
    if main_object.id == version_object.id:
        return False

    if isinstance(main_object, Opinion):
        fields_to_merge = [
            ("author_str", merge_judge_names),
            "author",
            "per_curiam",
            "joined_by",
            ("joined_by_str", merge_judge_names),
            "html_lawbox",
            "html_columbia",
            "xml_harvard",
        ]
    elif isinstance(main_object, OpinionCluster):
        fields_to_merge = cluster_fields_to_merge
    elif isinstance(main_object, Docket):
        fields_to_merge = docket_fields_to_merge
    else:
        fields_to_merge = []

    changed = False

    for field in fields_to_merge:
        merging_func = None
        if isinstance(field, tuple):
            field, merging_func = field

        main_value = getattr(main_object, field)
        version_value = getattr(version_object, field)
        if main_value:
            if not version_value:
                continue
            if main_value == version_value:
                continue
            if merging_func:
                setattr(
                    main_object,
                    field,
                    merging_func(main_value, version_value),
                )
                changed = True
                continue

            logger.warning(
                "Unexpected difference in %s: '%s' '%s'. %s: %s, %s",
                field,
                main_value,
                version_value,
                main_object._meta.model_name,
                main_object.id,
                version_object.id,
            )
        elif version_value:
            setattr(main_object, field, version_value)
            changed = True

    return changed


def merge_opinion_versions(
    main_opinion: Opinion, version_opinion: Opinion
) -> None:
    """Merge the version opinion and related objects into the main opinion

    Currently,this merges Opinion, OpinionClusters and Dockets
    It also changes the references on related objects such as Notes for Cluster
    and a whole list of  `models_that_reference_docket` for Dockets

    :param main_opinion: the main version
    :param version_opinion: the secondary version
    :return None
    """
    logger.info("Merging %s %s", main_opinion, version_opinion)
    update_main_opinion = merge_metadata(main_opinion, version_opinion)
    updated_main_cluster = merge_metadata(
        main_opinion.cluster, version_opinion.cluster
    )
    version_cluster = version_opinion.cluster

    main_docket = main_opinion.cluster.docket
    version_docket = version_opinion.cluster.docket
    is_same_docket = main_docket.id == version_docket.id
    updated_main_docket = merge_metadata(main_docket, version_docket)

    main_citations = {str(c) for c in main_opinion.cluster.citations.all()}

    with transaction.atomic():
        if update_main_opinion:
            main_opinion.save()
        if updated_main_cluster:
            main_opinion.cluster.save()
        if updated_main_docket:
            main_opinion.cluster.docket.save()

        update_referencing_objects(main_opinion.cluster, version_cluster)
        if not is_same_docket:
            update_referencing_objects(main_docket, version_docket)

        # update the cluster_id to prevent the version cluster deletion cascade
        for version_citation in version_cluster.citations.all():
            if str(version_citation) in main_citations:
                continue
            version_citation.cluster_id = main_opinion.cluster.id
            version_citation.save()

        version_opinion.cluster_id = main_opinion.cluster.id
        version_opinion.main_version = main_opinion
        version_opinion.save()

        # Both Opinion and Citation have a ForeignKey to OpinionCluster, with
        # on_delete=models.CASCADE. Also, there are signals (see
        # o_cluster_field_mapping) to delete the related Elasticsearch docs
        # So, deleting the cluster will delete any associated Citation,
        # and will delete the associated objects in ES
        version_cluster.delete()

        if not is_same_docket:
            version_docket.delete()

        # since the cluster was reassigned, this opinion was not deleted from
        # the ES index. We don't want versions to show up on search
        try:
            OpinionDocument.get(
                id=ES_CHILD_ID(version_opinion.id).OPINION
            ).delete()
        except NotFoundError:
            pass


def merge_versions_by_download_url(
    url_start: str, limit: int | None = None
) -> None:
    """Get opinion version candidates when they have the exact same download_url

    Note that this function applies only to scraped Opinions, which have a
    `download_url` field

    :param url_start: the general domain and directory parts of the URL as
        found on Opinion.download_url. For example, for `nev` opinions:
        'http://caseinfo.nvsupreme'
    :param limit: max number of groups to correct
    :return None
    """
    if url_start:
        query = get_query_from_url(url_start, "startswith")
    else:
        query = Q()

    qs = (
        Opinion.objects.filter(query)
        .exclude(Q(download_url="") | Q(download_url__isnull=True))
        .values("download_url")
        .annotate(
            number_of_rows=Count("download_url"),
            # compute the number of  distinct hashes to prevent colliding with
            # actual duplicates, which are not versions
            number_of_hashes=Count("sha1", distinct=True),
        )
        .order_by()
        .filter(number_of_rows__gte=2, number_of_hashes__gte=2)
    )

    # The groups queryset will look like
    # {'download_url': 'https://caseinfo.nvsupremecourt...',
    # 'number_of_rows': 2, 'number_of_hashes': 2}
    seen_urls = set()
    stats = defaultdict(lambda: 0)
    for group in qs:
        if limit and len(seen_urls) > limit:
            break

        standard_url = group["download_url"].replace("https", "http")
        if standard_url in seen_urls:
            continue
        seen_urls.add(standard_url)

        logger.info("Processing group %s", group)

        query = get_query_from_url(group["download_url"], "exact")
        # keep the latest opinion as the main version
        # exclude opinions that already have a main_version. If that main
        # version is a version of the current document, they will be updated
        # transitively
        main, *versions = (
            Opinion.objects.filter(query)
            .exclude(main_version__isnull=False)
            .select_related("cluster", "cluster__docket")
            .order_by("-date_created")
        )
        merge_versions_by_text_similarity(main, versions, stats)
        stats["seen_urls"] = len(seen_urls)

    logger.info(stats)


def comparable_dockets(docket: Docket, version_docket: Docket) -> bool:
    """
    Make sure that the dockets have at least the same court_id and docket number

    :param docket: the main docket
    :param version_docket: the version docket
    :return: True if dockets have the same court_id and docket number
    """
    # the same docket
    if docket.id == version_docket.id:
        return True

    log_template = "Different '%s' for docket %s and %s"

    if docket.court_id != version_docket.court_id:
        logger.error(log_template, "court_id", docket.id, version_docket.id)
        return False

    if docket.docket_number != version_docket.docket_number:
        logger.error(
            log_template, "docket_number", docket.id, version_docket.id
        )
        return False

    return True


def merge_versions_by_text_similarity(
    main_opinion: Opinion,
    versions: Union[QuerySet[Opinion], list[Opinion]],
    stats: dict,
) -> None:
    """Compare text of main and candidate version opinions; merge if similar

    :param main: the opinion that will be the main version
    :param versions: a list or queryset of opinions that will be compared
        to `main_opinion`, in order to decide if they should point to it
    :param stats: a dictionary to hold stats

    :return: None
    """
    main_text = clean_opinion_text(main_opinion)
    if not main_text:
        logger.warning("Opinion has no text %s", main_opinion.id)
        return

    for version in versions:
        if not comparable_dockets(
            main_opinion.cluster.docket, version.cluster.docket
        ):
            stats["different dockets"] += 1
            continue

        version_text = clean_opinion_text(version)
        if text_is_similar(main_text, version_text):
            stats["success"] += 1
            if DRY_RUN:
                continue
            merge_opinion_versions(main_opinion, version)

            if not version.versions.exists():
                continue

            # if the opinion that is now a version has versions itself,
            # make them point to the new main
            for version_to_update in version.versions.all():
                version_to_update.main_version = main_opinion
                version_to_update.save()
                stats["updated child versions"] += 1
        else:
            stats["text too different"] += 1
            logger.error(
                "Opinions grouped by URL have dissimilar text. Main: %s. Version %s",
                main_opinion.id,
                version.id,
            )


class Command(VerboseCommand):
    help = "Find and merge Opinion objects that are versions of each other"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "method",
            choices=["download_url", "docket"],
            help="""Currently we have researched 2 methods
            - `download_url`: group opinions by exact `download_url` match
            and confirm their text similarity
            - `docket`: group opinions by dockets, match by metadata and text
            similarity
            """,
        )
        parser.add_argument(
            "--url_template",
            default="",
            help="""The general domain and directory parts of the URL as found
            on Opinion.download_url. For example, for `nev` opinions:
            'http://caseinfo.nvsupreme'. If empty, will attempt to process all
            groups
            """,
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="""A limit of version groups to process""",
        )
        parser.add_argument(
            "--dry-run",
            default=False,
            action="store_true",
            help="""If passed, the command will run but no change will be saved
            """,
        )

        # for the `docket` method, we will need more arguments
        # - court_id
        # - source to limit, if any
        # - date ranges

    def handle(self, *args, **options):
        super().handle(*args, **options)
        if options["dry_run"]:
            global DRY_RUN
            DRY_RUN = True

        if options["method"] == "download_url":
            merge_versions_by_download_url(
                options["url_template"].strip(), options.get("limit")
            )

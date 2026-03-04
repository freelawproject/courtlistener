import itertools
import re
from collections import defaultdict
from difflib import Differ, SequenceMatcher

from django.db import transaction
from django.db.models import Count, F, Q, QuerySet
from eyecite import clean_text

from cl.alerts.models import DocketAlert
from cl.audio.models import Audio
from cl.citations.parenthetical_utils import create_parenthetical_groups
from cl.favorites.models import DocketTag, Note
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.models import (
    AttorneyOrganizationAssociation,
    PartyType,
    Role,
)
from cl.recap.models import PacerFetchQueue, ProcessingQueue
from cl.scrapers.exceptions import MergingError
from cl.scrapers.models import PACERMobilePageData
from cl.search.documents import ES_CHILD_ID, OpinionDocument
from cl.search.models import (
    SOURCES,
    BankruptcyInformation,
    Citation,
    Claim,
    ClusterRedirection,
    Docket,
    DocketEntry,
    DocketPanel,
    DocketTags,
    Opinion,
    OpinionCluster,
    OpinionClusterNonParticipatingJudges,
    OpinionClusterPanel,
    OpinionJoinedBy,
    OpinionsCited,
    Parenthetical,
)
from cl.search.tasks import remove_document_from_es_index

MIN_SEQUENCE_SIMILARITY_STRICT = 0.9
MIN_SEQUENCE_SIMILARITY_LOOSE = 0.7
DRY_RUN = False


def explain_version_differences(
    opinions: list[Opinion | int],
    text_field: str = "plain_text",
    verbose: bool = False,
) -> None:
    """Debugging function to inspect version differences

    :param opinions: a list of Opinion objects or ids
    :param text_field: the field that holds the opinion's content
    :param verbose: pass True to print all the differences between texts
    :return None
    """
    if isinstance(opinions[0], int):
        opinions = [
            Opinion.objects.get(id=opinion_id) for opinion_id in opinions
        ]
    id_to_op = {op.id: op for op in opinions}

    text_combinations = itertools.combinations(
        [
            (opinion.id, getattr(opinion, text_field).strip())
            for opinion in opinions
        ],
        2,
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
        base_cl_url = "https://www.courtlistener.com/opinion/"
        print(f"{base_cl_url}{id_to_op[op1].cluster_id}/x/")
        print(f"{base_cl_url}{id_to_op[op2].cluster_id}/x/")

        if verbose:
            for index, i in enumerate(differ.compare(text1, text2)):
                if i[0] in "-+?":
                    if not prev_index or (
                        prev_index == index - 1 and prev_key == i[0]
                    ):
                        diff += i[-1]
                    else:
                        print(
                            f"difference at index {index} is {prev_key} {repr(diff)}"
                        )
                        diff = ""
                    prev_key = i[0]
                    prev_index = index
                elif diff:
                    print(
                        f"difference at index {index} is {prev_key} {repr(diff)}"
                    )
                    diff = ""

        sm = SequenceMatcher(None, text1, text2)
        print("SequenceMatcher.ratio(text1, text2)", sm.ratio())
        sm = SequenceMatcher(None, text2, text1)
        print("SequenceMatcher.ratio(text2, text1)", sm.ratio())


models_that_reference_docket = [
    # (model, related name to the docket, unique together field)
    (DocketAlert, "docket", "user_id"),
    (Audio, "docket", None),
    (DocketTags, "docket", None),
    (Note, "docket_id", "user_id"),
    (
        AttorneyOrganizationAssociation,
        "docket",
        ("attorney_organization_id", "attorney_id"),
    ),
    (PartyType, "docket", ("party_id", "name")),
    (Role, "docket", ("party_id", "attorney_id", "date_action", "role")),
    (PacerFetchQueue, "docket", None),
    (ProcessingQueue, "docket", None),
    (PACERMobilePageData, "docket", "docket_id"),
    (BankruptcyInformation, "docket", "docket_id"),
    (Claim, "docket", None),
    (DocketPanel, "docket", "person_id"),
    (DocketEntry, "docket", None),
    (DocketTag, "docket", "tag_id"),
    (OpinionCluster, "docket", None),
]


models_that_reference_cluster = [
    # (model, related name to the cluster, unique together field)
    (
        Note,
        "cluster_id",
        "user_id",
    ),
    (Opinion, "cluster", None),
    (OpinionClusterPanel, "opinioncluster", "person_id"),
    (OpinionClusterNonParticipatingJudges, "opinioncluster", "person_id"),
    (Citation, "cluster", ("reporter", "page", "volume")),
]

models_that_reference_opinion = [(OpinionJoinedBy, "opinion", "person_id")]


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
    # panel and non_participating_judges taken care of via
    # `update_referencing_objects`
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


def group_opinions_by_url(query: Q) -> QuerySet:
    """Get duplicate candidates queryset by grouping opinions by `download_url`

    :param query: a Q object to filter the opinions
    :return: the opinion groups queryset
    """
    qs = (
        Opinion.objects.filter(query)
        .exclude(Q(download_url="") | Q(download_url__isnull=True))
        .values("download_url")
        .annotate(
            number_of_rows=Count("download_url"),
            number_of_hashes=Count("sha1", distinct=True),
        )
        .order_by()
        # compute the number of  distinct hashes to prevent colliding with
        # actual duplicates, which will be handled in another command
        .filter(number_of_rows__gte=2, number_of_hashes__gte=2)
    )
    return qs


def get_same_url_opinions(
    opinion_group: dict, seen_urls: set
) -> QuerySet | None:
    """Given a URL, get a queryset for all opinions with that URL

    :param opinion_group: a dictionary with a 'download_url' key
    :param seen_urls: a set to keep track of seen URLs.
        Useful to skip urls we have already processed
    :return: a queryset or None
    """
    standard_url = opinion_group["download_url"].replace("https", "http")
    if standard_url in seen_urls:
        return

    seen_urls.add(standard_url)
    download_url_query = get_query_from_url(
        opinion_group["download_url"], "exact"
    )
    return (
        Opinion.objects.filter(download_url_query)
        .filter(cluster__source=SOURCES.COURT_WEBSITE)
        .select_related("cluster", "cluster__docket")
        .order_by("-date_created")
    )


def clean_opinion_text(opinion: Opinion) -> str:
    """Remove noise (HTML tags or extra whitespace) from an opinion's text

    :param opinion: the opinion
    :return: the cleaned text
    """
    if opinion.html:
        return clean_text(opinion.html, ["html", "all_whitespace"])

    return re.sub(r"\s+", " ", opinion.plain_text)


def get_text_similarity(text1: str, text2: str) -> tuple[bool, float, float]:
    """Check if the text from both opinions is the same or very similar

    A single character difference yields a 0.999 ratio
    A single word difference may reduce the similarity a few points,
    depending on how long the sequence is, and if it is an addition/removal
    or a correction. In general, a 0.9 MIN value should tolerate a difference
    of a few words between versions, which is what we expect
    Note that this in sensible to argument order, so we retry with inverted
    order if the first run fails

    :param text1: a cleaned opinion's text
    :param text2: another cleaned opinion's text
    :return: a tuple with:
        True in the first member if any of the text similarity ratios was
            greater than the strict threshold
        True in the second member if any of the ratios was greater than the
            loose threshold
        the ratios in the third and fourth member
    """
    if text1 == text2:
        return True, True, 1.0, 1.0

    ratio2 = 1.0

    ratio1 = SequenceMatcher(None, text1, text2).ratio()
    if ratio1 >= MIN_SEQUENCE_SIMILARITY_STRICT:
        return True, True, ratio1, ratio2

    ratio2 = SequenceMatcher(None, text2, text1).ratio()

    if ratio2 >= MIN_SEQUENCE_SIMILARITY_STRICT:
        return True, True, ratio1, ratio2

    return (
        False,
        ratio1 > MIN_SEQUENCE_SIMILARITY_LOOSE
        or ratio2 > MIN_SEQUENCE_SIMILARITY_LOOSE,
        ratio1,
        ratio2,
    )


def update_referencing_objects(
    main_object: Docket | OpinionCluster | Opinion,
    version_object: Docket | OpinionCluster | Opinion,
) -> None:
    """Make all objects referencing to `version_object` point to `main_object`

    This way, prevent cascade deletion. Unique constraints are handled:
    - no constraints, a naive update is performed
    - there is a single key constraint (like JoinedBy -> Opinion)
    - there are multiple key constraints (like Citation -> OpinionCluster)

    :param main_object: the main version OpinionCluster or Docket
    :param version_object: the secondary version OpinionCluster or Docket
    """
    if isinstance(main_object, OpinionCluster):
        referencing_models = models_that_reference_cluster
    elif isinstance(main_object, Docket):
        referencing_models = models_that_reference_docket
    elif isinstance(main_object, Opinion):
        referencing_models = models_that_reference_opinion

    for model, related_name, unique_together in referencing_models:
        filter_query = {related_name: version_object}
        update_query = existing_for_main_object_query = {
            related_name: main_object
        }

        related_to_version_qs = model.objects.filter(**filter_query)
        if not related_to_version_qs.exists():
            continue

        logger.info(
            "Updating related %s for %s %s",
            model._meta.model_name,
            main_object._meta.model_name,
            main_object.id,
        )
        if not unique_together:
            related_to_version_qs.update(**update_query)
            continue

        if isinstance(unique_together, str):
            existing_for_main = (
                model.objects.filter(**existing_for_main_object_query)
                .only(unique_together)
                .values_list(unique_together, flat=True)
            )
            exclude_query = {f"{unique_together}__in": existing_for_main}

            # for the objects that point to the version, exclude the ids that
            # already point to main; update the rest. When the version is
            # deleted the stragglers will be cascade deleted
            related_to_version_qs.exclude(**exclude_query).update(
                **update_query
            )
            continue

        # final case, we need to compare over many unique together fields
        related_to_version = related_to_version_qs.only(
            *[f for f in unique_together] + ["id"]
        )
        related_to_main = model.objects.filter(
            **existing_for_main_object_query
        ).only(*unique_together)
        main_objects = {
            tuple(getattr(obj, field) for field in unique_together)
            for obj in related_to_main
        }

        for obj in related_to_version:
            if (
                tuple(getattr(obj, field) for field in unique_together)
                in main_objects
            ):
                continue

            # use .save to trigger signals. Useful for `Citation`
            setattr(obj, related_name, main_object)
            obj.save()


def merge_metadata(
    main_object: Opinion | OpinionCluster | Docket,
    version_object: Opinion | OpinionCluster | Docket,
    error_on_diff: bool = False,
) -> bool:
    """Merge `fields_to_merge` from `version_object` into `main_object`

    :param main_object: the main OpinionCluster or Opinion or Docket
    :param version_object: the secondary version Opinion, or its OpinionCluster
    :param error_on_diff: raise an exception if there is an unexpected difference

    :return: True if the main object was updated and needs to be saved
    """
    if main_object.id == version_object.id:
        return False

    if isinstance(main_object, Opinion):
        fields_to_merge = [
            ("author_str", merge_judge_names),
            "author",
            "per_curiam",
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

            warning_template = (
                "Unexpected difference in %s: '%s' '%s'. %s: %s, %s"
            )
            warning_values = (
                field,
                main_value,
                version_value,
                main_object._meta.model_name,
                main_object.id,
                version_object.id,
            )
            if error_on_diff:
                raise MergingError(warning_template % warning_values)

            logger.warning(warning_template, *warning_values)
        elif version_value:
            setattr(main_object, field, version_value)
            changed = True

    return changed


def delete_version_related_objects(version: Opinion) -> None:
    """Delete objects related to citations that point to the version

    :param version: the versioned opinion
    :return None
    """
    # Decrease citation_count of all clusters cited by the version
    cited_clusters = (
        version.opinions_cited.all()
        .only("cluster_id")
        .values_list("cluster_id", flat=True)
    )
    if cited_clusters:
        OpinionCluster.objects.filter(id__in=list(cited_clusters)).update(
            citation_count=F("citation_count") - 1
        )

    OpinionsCited.objects.filter(
        Q(citing_opinion_id=version.id) | Q(cited_opinion_id=version.id)
    ).delete()

    described_by_version = Parenthetical.objects.filter(
        describing_opinion_id=version.id
    )
    if described_by_version.exists():
        # recompute parenthetical groups for clusters described by the version
        ids = described_by_version.only(
            "describing_opinion__cluster_id"
        ).values_list("describing_opinion__cluster_id", flat=True)
        Parenthetical.objects.filter(
            Q(described_opinion_id=version.id)
            | Q(describing_opinion_id=version.id)
        ).delete()
        for cluster in OpinionCluster.objects.filter(id__in=ids):
            create_parenthetical_groups(cluster)

    else:
        Parenthetical.objects.filter(described_opinion_id=version.id).delete()

    version.unmatched_citations.all().delete()
    version.citing_documents.all().delete()


def merge_opinion_versions(
    main_opinion: Opinion,
    version_opinion: Opinion,
    strict_merging: bool = False,
) -> None:
    """Merge the version opinion and related objects into the main opinion

    Currently,this merges Opinion, OpinionClusters and Dockets
    It also changes the references on related objects such as Notes for Cluster
    and a whole list of  `models_that_reference_docket` for Dockets

    :param main_opinion: the main version
    :param version_opinion: the secondary version
    :param strict_merging: all metadata fields should be the same on the
        opinion and cluster for the merge to succeed
    :return None
    """
    logger.info("Merging %s %s", main_opinion, version_opinion)
    update_main_opinion = merge_metadata(
        main_opinion, version_opinion, strict_merging
    )
    updated_main_cluster = merge_metadata(
        main_opinion.cluster, version_opinion.cluster, strict_merging
    )
    version_cluster = version_opinion.cluster

    main_docket = main_opinion.cluster.docket
    version_docket = version_opinion.cluster.docket
    is_same_docket = main_docket.id == version_docket.id
    updated_main_docket = merge_metadata(main_docket, version_docket)

    with transaction.atomic():
        if update_main_opinion:
            main_opinion.save()
        if updated_main_cluster:
            main_opinion.cluster.save()
        if updated_main_docket:
            main_opinion.cluster.docket.save()

        update_referencing_objects(main_opinion, version_opinion)

        update_referencing_objects(main_opinion.cluster, version_cluster)
        if not is_same_docket:
            update_referencing_objects(main_docket, version_docket)

        version_opinion.cluster_id = main_opinion.cluster.id
        version_opinion.main_version = main_opinion
        version_opinion.html_with_citations = ""
        version_opinion.save()
        delete_version_related_objects(version_opinion)

        # since the cluster was reassigned, this opinion was not cascade
        # deleted, and then deleted from the ES index. We don't want versions
        # to show up on search
        remove_document_from_es_index.delay(
            OpinionDocument.__name__,
            ES_CHILD_ID(version_opinion.id).OPINION,
            version_cluster.id,
        )

        ClusterRedirection.create_from_clusters(
            main_opinion.cluster, version_cluster, ClusterRedirection.VERSION
        )

        # Both Opinion and Citation have a ForeignKey to OpinionCluster, with
        # on_delete=models.CASCADE. Also, there are signals (see
        # o_cluster_field_mapping) to delete the related Elasticsearch docs
        # So, deleting the cluster will delete any associated Citation,
        # and will delete the associated objects in ES
        version_cluster.delete()

        if not is_same_docket:
            version_docket.delete()


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

    query = query & Q(cluster__source=SOURCES.COURT_WEBSITE)
    qs = group_opinions_by_url(query)

    # The groups queryset will look like
    # {'download_url': 'https://caseinfo.nvsupremecourt...',
    # 'number_of_rows': 2, 'number_of_hashes': 2}
    seen_urls = set()
    stats = defaultdict(lambda: 0)
    for group in qs:
        if limit and len(seen_urls) > limit:
            break

        versions_queryset = get_same_url_opinions(group, seen_urls).exclude(
            main_version__isnull=False
        )
        if versions_queryset is None:
            continue

        # keep the latest opinion as the main version
        # exclude opinions that already have a main_version. If that main
        # version is a version of the current document, they will be updated
        # transitively
        main, *versions = versions_queryset
        merge_versions_by_text_similarity(main, versions, stats)
        stats["seen_urls"] = len(seen_urls)

    logger.info(stats)


def comparable_dockets(docket: Docket, version_docket: Docket) -> bool:
    """
    Make sure that the dockets have at least the same court_id and docket number

    Special case: For New York courts, skip the docket number check since newer
    versions may not have a docket number in the opinion text, which would
    otherwise prevent versioning from working.


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

    # Special case for NY courts: allow versioning without matching docket numbers
    # when at least one docket number is empty.
    if docket.court_id.startswith("ny") and (
        not docket.docket_number or not version_docket.docket_number
    ):
        return True

    if docket.docket_number != version_docket.docket_number:
        logger.error(
            log_template, "docket_number", docket.id, version_docket.id
        )
        return False

    return True


def merge_versions_by_text_similarity(
    main_opinion: Opinion,
    versions: QuerySet[Opinion] | list[Opinion],
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
        text_is_strictly_similar, text_is_loosely_similar, ratio1, ratio2 = (
            get_text_similarity(main_text, version_text)
        )

        if text_is_strictly_similar or text_is_loosely_similar:
            if text_is_loosely_similar:
                stats["loose text similarity"] += 1

            stats["success"] += 1
            if DRY_RUN:
                continue

            # if the text_is_loosely_similar, all opinion and cluster metadata
            # fields must be the same for 2 versions to be merged
            try:
                merge_opinion_versions(
                    main_opinion, version, not text_is_strictly_similar
                )
            except MergingError:
                stats["merging error"] += 1
                continue

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
                extra={"ratio1": ratio1, "ratio2": ratio2},
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

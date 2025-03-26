import itertools
import re
from collections import defaultdict
from difflib import Differ, SequenceMatcher
from typing import Union

from django.db import transaction
from django.db.models import Count, Q
from elasticsearch import NotFoundError
from eyecite import clean_text

from cl.favorites.models import Note
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.documents import ES_CHILD_ID, OpinionDocument
from cl.search.models import Opinion, OpinionCluster

MIN_SEQUENCE_SIMILARITY = 0.9


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
            > MIN_SEQUENCE_SIMILARITY
        )
    return ratio


def merge_metadata(
    main_object: Union[Opinion, OpinionCluster],
    version_object: Union[Opinion, OpinionCluster],
    fields_to_merge: list[str],
) -> bool:
    """Merge `fields_to_merge` from `version_object` into `main_object`

    :param main_object: the main OpinionCluster or Opinion
    :param version_object: the secondary version Opinion, or its OpinionCluster
    :param fields_to_merge: a list of field names to merge
    """
    changed = False

    for field in fields_to_merge:
        main_value = getattr(main_object, field)
        version_value = getattr(version_object, field)
        if main_value:
            if version_value and not main_value == version_value:
                logger.warning(
                    "Unexpected difference in %s: '%s' '%s'. Opinions: %s, %s",
                    field,
                    main_value,
                    version_value,
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

    Currently,this merges OpinionClusters, Citations, and Notes
    In the future, we may want to also merge Dockets spread apart that belong
    together

    :param main_opinion: the main version
    :param version_opinion: the secondary version
    :return None
    """
    opinion_fields = [
        "author_str",
        "author",
        "per_curiam",
        "joined_by",
        "joined_by_str",
        "html_lawbox",
        "html_columbia",
        "xml_harvard",
    ]
    cluster_fields = [
        "judges",
        "case_name_short",
        "case_name_full",
        "procedural_history",
        "attorneys",
        "nature_of_suit",
        "posture",
        "syllabus",
        "blocked",
        "date_blocked",
        "headnotes",
        "cross_reference",
        "correction",
        "disposition",
        "other_dates",
        "summary",
        "arguments",
        "headmatter",
    ]
    update_main_opinion = merge_metadata(
        main_opinion, version_opinion, opinion_fields
    )
    updated_main_cluster = merge_metadata(
        main_opinion.cluster, version_opinion.cluster, cluster_fields
    )

    version_cluster = version_opinion.cluster
    update_notes = Note.objects.filter(cluster_id=version_cluster.id).exists()

    # Citations
    citations = {str(c) for c in main_opinion.cluster.citations.all()}

    with transaction.atomic():
        if update_main_opinion:
            main_opinion.save()
        if updated_main_cluster:
            main_opinion.cluster.save()
        if update_notes:
            Note.objects.filter(cluster_id=version_cluster.id).update(
                cluster_id=main_opinion.cluster.id
            )

        # update the cluster_id to prevent the version cluster deletion cascade
        for version_citation in version_cluster.citations.all():
            if str(version_citation) in citations:
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
    query = get_query_from_url(url_start, "startswith")
    qs = (
        Opinion.objects.filter(query)
        .exclude(download_url="")
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
        if group["download_url"].replace("https", "http") in seen_urls:
            continue

        seen_urls.add(group["download_url"].replace("https", "http"))

        if limit and len(seen_urls) > limit:
            break

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


def merge_versions_by_text_similarity(
    main: Opinion, versions: list[Opinion], stats: dict
) -> None:
    """Compare text of main and candidate version opinions; merge if similar

    :param main: the opinion that will be the main version
    :param versions: a list of opinions that will be compared to `main`, in
        order to decide if they should point to it
    :param stats: a dictionary to hold stats

    :return: None
    """
    main_text = clean_opinion_text(main)
    if not main_text:
        logger.warning("Opinion has no text %s", main.id)
        return

    for version in versions:
        # we should investigate this case further
        if main.cluster.docket.id != version.cluster.docket.id:
            stats["different dockets"] += 1
            logger.error(
                "Main opinion docket %s is not the same as version docket %s",
                main.cluster.docket.id,
                version.cluster.docket.id,
            )
            continue

        version_text = clean_opinion_text(version)
        if text_is_similar(main_text, version_text):
            merge_opinion_versions(main, version)
            stats["success"] += 1

            if not version.versions.exists():
                continue

            # if the opinion that is now a version has versions itself,
            # make them point to the new main
            for version_to_update in version.versions.all():
                version_to_update.main_version = main
                version_to_update.save()
                stats["updated child versions"] += 1
        else:
            stats["text too different"] += 1
            logger.error(
                "Opinions grouped by URL have disimilar text. Main: %s. Version %s",
                main.id,
                version.id,
            )


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
        for index, i in enumerate(differ.compare(text1, text2)):
            if i[0] in "-+?":
                print(
                    f"Difference between {op1} {op2} at index {index} is {repr(i)}"
                )

        sm = SequenceMatcher(None, text1, text2)
        print("SequenceMatcher ratio", sm.ratio())


class Command(VerboseCommand):
    help = "Find and merge Opinion objects that are versions of each other"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "method",
            choices=["download_url", "docket"],
            required=True,
            help="""Currently we have researched 2 methods
            - `download_url`: group opinions by exact `download_url` match
            and confirm their text similarity
            - `docket`: group opinions by dockets, match by metadata and text
            similarity
            """,
        )
        parser.add_argument(
            "url_template",
            required=False,
            help="""The general domain and directory parts of the URL as found
            on Opinion.download_url. For example, for `nev` opinions:
            'http://caseinfo.nvsupreme'""",
        )
        parser.add_argument(
            "--limit",
            required=False,
            type=int,
            help="""A limit of version groups to process""",
        )

        # for the `docket` method, we will need more arguments
        # - court_id
        # - source to limit, if any
        # - date ranges

    def handle(self, *args, **options):
        super().handle(*args, **options)
        if options["method"] == "download_url":
            merge_versions_by_download_url(
                options["url_template"], options.get("limit")
            )

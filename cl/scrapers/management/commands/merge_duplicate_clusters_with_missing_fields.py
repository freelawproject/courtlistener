import re
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import Count

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Citation, Opinion, OpinionCluster

# Helper methods for the main method def handle(self, *args, **kwargs):


# Method for merging citations. If citations of the duplicate misses some information, add it from another duplicate
def merge_citations(keeper, clust):
    keeper_citations = list(Citation.objects.filter(cluster=keeper))
    clust_citations = Citation.objects.filter(cluster=clust)

    for c in clust_citations:
        matched = None
        citation_fields = ["volume", "reporter", "page", "type"]

        for k in keeper_citations:
            conflict_found = False
            for field in citation_fields:
                k_val = getattr(k, field)
                c_val = getattr(c, field)
                if k_val not in None and c_val not in None and k_val != c_val:
                    conflict_found = True
                    break

            if not conflict_found:
                matched = k
                break

        # If no conflict, either merge missing fields or move if no exact duplicate
        if matched:
            citation_fields = ["volume", "reporter", "page", "type"]
            for field in citation_fields:
                keeper_val = getattr(matched, field)
                c_val = getattr(c, field)
                if keeper_val in [None, ""] and c_val not in [None, ""]:
                    setattr(matched, field, c_val)

            # Save only if no duplicate exists
            if (
                not Citation.objects.filter(
                    cluster=keeper,
                    volume=matched.volume,
                    reporter=matched.reporter,
                    page=matched.page,
                )
                .exclude(id=matched.id)
                .exists()
            ):
                matched.save()
        else:
            # Move only if exact duplicate doesn't exist
            if not Citation.objects.filter(
                cluster=keeper,
                volume=c.volume,
                reporter=c.reporter,
                page=c.page,
            ).exists():
                c.cluster = keeper
                c.save()


# Method for identifying the level of similarity of two texts. Uses SequenceMatcher.
def text_is_similar(keeper_val, clust_val):
    if not keeper_val or not clust_val:
        return 1
    return SequenceMatcher(None, keeper_val, clust_val).ratio() >= 0.75


# Method for extracting metadata from the textual opinion using re.
def extract_opinion_metadata(text):
    data = {}

    # Find case name in the text
    case_name_match = re.match(
        r"\s*(.*?)\s*\r?\n\d{4}\s+[A-Z]{1,3}\s+\d+", text
    )
    data["case_name"] = (
        case_name_match.group(1).strip() if case_name_match else None
    )

    # Find docket number or case number in the text
    docket_match = re.search(r"Case Number:\s*(\d+)", text)
    data["docket_number"] = (
        docket_match.group(1).strip() if docket_match else None
    )

    # Find court in the text
    court_match = re.search(r"\n([A-Z\s]+COURT.*)", text)
    data["court"] = court_match.group(1).strip() if court_match else None

    # Find attorneys in the text
    attorneys = re.findall(
        r"(\*?\d*\s*[A-Z][A-Za-z\s\.]+,.*?,\s*for (?:Plaintiff|Defendant)/Appellee)",
        text,
    )
    data["attorneys"] = attorneys
    print(attorneys)

    return data


# Method for filling absent metadata obtained from the text of the opinion.
def fill_opinion_metadata(opinion: Opinion):
    text = opinion.plain_text
    data = extract_opinion_metadata(text)
    cluster = opinion.cluster

    # Merging fields if found some fields in the text of the opinion
    if data.get("court") and not cluster.docket.court:
        cluster.docket.court = data["case_name"]
        cluster.docket.save()

    if data.get("case_name") and not cluster.case_name:
        cluster.case_name = data["case_name"]
        cluster.save()

    if data.get("attorneys") and not cluster.attorneys:
        cluster.attorneys = "; ".join(data["attorneys"])
        cluster.save()

    if data.get("docket_number") and cluster.docket.docket_number == "Unknown":
        cluster.docket.docket_number = data["docket_number"]
        cluster.docket.save()


# Method for identifying if clusters can be merged. Compares fields of one cluster to another and opinions.
def ready_to_merge(keeper, clust):
    keeper_opinions = list(Opinion.objects.filter(cluster=keeper))
    other_cluster_opinions = list(Opinion.objects.filter(cluster=clust))

    # Checking if clusters opinions have conflicts
    for other_cluster_opinion in other_cluster_opinions:
        for keeper_opinion in keeper_opinions:
            # If opinions types are the same, their texts should match
            if other_cluster_opinion.type == keeper_opinion.type:
                # Only merge opinions if there are no conflicts
                if (
                    other_cluster_opinion.plain_text
                    != keeper_opinion.plain_text
                ):
                    return 0

    # Dictionary for the fields to check
    fields_to_check = {
        "summary": (keeper.summary, clust.summary),
        "syllabus": (keeper.syllabus, clust.syllabus),
        "arguments": (keeper.arguments, clust.arguments),
        "headnotes": (keeper.headnotes, clust.headnotes),
        "headmatter": (keeper.headmatter, clust.headmatter),
        "citation_count": (keeper.citation_count, clust.citation_count),
        "scdb_votes_majority": (
            keeper.scdb_votes_majority,
            clust.scdb_votes_majority,
        ),
        "scdb_votes_minority": (
            keeper.scdb_votes_minority,
            clust.scdb_votes_minority,
        ),
        "scdb_decision_direction": (
            keeper.scdb_decision_direction,
            clust.scdb_decision_direction,
        ),
        "scdb_id": (keeper.scdb_id, clust.scdb_id),
        "slug": (keeper.slug, clust.slug),
        "judges": (keeper.judges, clust.judges),
        "attorneys": (keeper.attorneys, clust.attorneys),
        "nature_of_suit": (keeper.nature_of_suit, clust.nature_of_suit),
        "posture": (keeper.posture, clust.posture),
        "disposition": (keeper.disposition, clust.disposition),
        "history": (keeper.history, clust.history),
        "other_dates": (keeper.other_dates, clust.other_dates),
        "cross_reference": (keeper.cross_reference, clust.cross_reference),
        "correction": (keeper.correction, clust.correction),
    }

    # Getting opinions from clusters
    keeper_citations = Citation.objects.filter(cluster=keeper)
    other_cluster_citations = Citation.objects.filter(cluster=clust)

    # Checking if citations have conflicts
    for other_cluster_citation in other_cluster_citations:
        for keeper_citation in keeper_citations:
            for field in ["volume", "reporter", "page"]:
                keeper_citation_val = getattr(keeper_citation, field)
                other_cluster_citation_val = getattr(
                    other_cluster_citation, field
                )

                if (
                    (keeper_citation_val not in None)
                    and (other_cluster_citation_val not in None)
                    and (keeper_citation_val != other_cluster_citation_val)
                ):
                    return 0

    # Checking if fields are similar or same"
    for field_name, (keeper_val, clust_val) in fields_to_check.items():
        # Checking similarity of the textual fields like "syllabus"
        if field_name in [
            "syllabus",
            "summary",
            "arguments",
            "headnotes",
            "headmatter",
        ]:
            if (
                keeper_val
                and clust_val
                and not text_is_similar(keeper_val, clust_val)
            ):
                return 0
        else:
            if keeper_val and clust_val and keeper_val != clust_val:
                return 0

    return 1


# Command method
class Command(VerboseCommand):
    help = "Merges clusters with retrieving information from the text of the opinion"

    def handle(self, *args, **kwargs):
        super().handle(*args, **kwargs)

        # Filter clusters with the same case name
        duplicates = (
            OpinionCluster.objects.values("case_name")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
        )

        # Wraps single database transaction
        with transaction.atomic():
            # The most outer loop for all duplicates
            for dup in duplicates:
                clusters = list(
                    OpinionCluster.objects.filter(
                        case_name=dup["case_name"]
                    ).order_by("id")
                )

                # Keeps track of deleted clusters' IDs from the database
                deleted_ids = set()

                # The loop traversing clusters with one case name
                for i in range(len(clusters)):
                    keeper = clusters[i]

                    if keeper.id in deleted_ids:
                        continue

                    # Filling metadata from the opinions text
                    for opinion in Opinion.objects.filter(cluster=keeper):
                        fill_opinion_metadata(opinion)

                    for j in range(i + 1, len(clusters)):
                        other_cluster = clusters[j]

                        if other_cluster.id in deleted_ids:
                            continue

                        # Checking if court and docket_number are equal#
                        if (
                            keeper.docket.court.fjc_court_id
                            != other_cluster.docket.court.fjc_court_id
                        ):
                            continue

                        if (
                            keeper.docket.docket_number
                            != other_cluster.docket.docket_number
                        ):
                            continue
                        # ---------------------------------------------#

                        # Cheking if the opinions can be merged
                        if ready_to_merge(keeper, other_cluster) == 0:
                            continue

                        other_cluster_opinions = list(
                            Opinion.objects.filter(cluster=other_cluster)
                        )

                        # Merging opinions
                        for opinion in other_cluster_opinions:
                            opinion.cluster = keeper
                            opinion.save()

                        # Merging judges
                        for judge in other_cluster.panel.all():
                            keeper.panel.add(judge)
                        for (
                            judge
                        ) in other_cluster.non_participating_judges.all():
                            keeper.non_participating_judges.add(judge)

                        # Fields that need to be merged
                        fields_to_transfer = {
                            "summary": (keeper.summary, other_cluster.summary),
                            "syllabus": (
                                keeper.syllabus,
                                other_cluster.syllabus,
                            ),
                            "arguments": (
                                keeper.arguments,
                                other_cluster.arguments,
                            ),
                            "headnotes": (
                                keeper.headnotes,
                                other_cluster.headnotes,
                            ),
                            "headmatter": (
                                keeper.headmatter,
                                other_cluster.headmatter,
                            ),
                            "citation_count": (
                                keeper.citation_count,
                                other_cluster.citation_count,
                            ),
                            "scdb_votes_majority": (
                                keeper.scdb_votes_majority,
                                other_cluster.scdb_votes_majority,
                            ),
                            "scdb_votes_minority": (
                                keeper.scdb_votes_minority,
                                other_cluster.scdb_votes_minority,
                            ),
                            "scdb_decision_direction": (
                                keeper.scdb_decision_direction,
                                other_cluster.scdb_decision_direction,
                            ),
                            "scdb_id": (keeper.scdb_id, other_cluster.scdb_id),
                            "slug": (keeper.slug, other_cluster.slug),
                            "judges": (keeper.judges, other_cluster.judges),
                            "attorneys": (
                                keeper.attorneys,
                                other_cluster.attorneys,
                            ),
                            "nature_of_suit": (
                                keeper.nature_of_suit,
                                other_cluster.nature_of_suit,
                            ),
                            "posture": (keeper.posture, other_cluster.posture),
                            "disposition": (
                                keeper.disposition,
                                other_cluster.disposition,
                            ),
                            "history": (keeper.history, other_cluster.history),
                            "other_dates": (
                                keeper.other_dates,
                                other_cluster.other_dates,
                            ),
                            "cross_reference": (
                                keeper.cross_reference,
                                other_cluster.cross_reference,
                            ),
                            "correction": (
                                keeper.correction,
                                other_cluster.correction,
                            ),
                        }

                        # Transfering fields to the keeper
                        for field_name, (
                            kep,
                            other_cluster_value,
                        ) in fields_to_transfer.items():
                            keeper_val = getattr(keeper, field_name)

                            # If keeper doesn't have a value for the field, merge it from other_cluster
                            if not keeper_val and other_cluster_value:
                                setattr(
                                    keeper, field_name, other_cluster_value
                                )

                        # Merge citations
                        merge_citations(keeper, other_cluster)

                        # Save keeper in a database and delete other_cluster when merged
                        keeper.save()
                        other_cluster.delete()
                        deleted_ids.add(other_cluster.id)

                logger.info(
                    f"Merged validated duplicates for case: {dup['case_name']}"
                )

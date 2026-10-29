"""Sealing and deletion-blocker logic for OpinionClusters and RECAPDocuments.

Sealing means something slightly different for each: a RECAPDocument keeps
its row (flagged `is_sealed`) with its files scrubbed, while sealing an
OpinionCluster hard-deletes the cluster/opinion rows outright and leaves a
ClusterRedirection behind so the old URLs 410. What they share is the need
to clean the underlying files out of S3, Internet Archive, and CloudFront,
and to drop the citations mined from the sealed text, so nothing is left
reachable after the seal. Centralizing that here, rather than in the
admin, means callers just invoke a function instead of re-implementing
storage/CDN cleanup themselves.

Also holds the deletion-blocker checks that gate OpinionCluster sealing:
since sealing hard-deletes the cluster (and maybe its docket), anything
that still points at either one has to be checked for first, and that
check lives alongside the delete it protects rather than in the admin.
"""

import time
from typing import Any
from urllib import parse

import botocore.exceptions
import requests
from django.conf import settings
from django.db import transaction
from django.db.models import FileField, Q, QuerySet
from django.urls import reverse
from requests import Response

from cl.lib.cloud_front import invalidate_cloudfront
from cl.lib.decorators import retry
from cl.lib.models import THUMBNAIL_STATUSES
from cl.search.models import (
    CaseTransfer,
    ClusterRedirection,
    OpinionCluster,
    RECAPDocument,
)
from cl.search.tasks import update_es_document
from cl.visualizations.models import SCOTUSMap


def delete_from_ia(url: str) -> Response:
    """Delete an item from Internet Archive by URL

    :param url: The URL of the item, for example,
    https://archive.org/download/gov.uscourts.nyed.299029/gov.uscourts.nyed.299029.30.0.pdf
    :return: The requests.Response of the request to IA.
    """
    # Get the path and drop the /download/ part of it to just get the bucket
    # and the path
    path = parse.urlparse(url).path
    bucket_path = path.split("/", 2)[2]
    storage_domain = "https://s3.us.archive.org"
    return requests.delete(
        f"{storage_domain}/{bucket_path}",
        headers={
            "Authorization": f"LOW {settings.IA_ACCESS_KEY}:{settings.IA_SECRET_KEY}",
            "x-archive-cascade-delete": "1",
        },
        timeout=60,
    )


def delete_document_citations(rd: RECAPDocument) -> None:
    """Delete the case law citations mined from a RECAPDocument's text.

    Meant for documents that are being sealed: their text is scrubbed, so
    the citations extracted from it have to go too. Left in place, the
    sealed filing keeps appearing in its docket's authorities and in the
    "Cited By" lists of the opinions it referenced, and the leftover rows
    show up as related objects if the document is later deleted outright.

    Also pushes the now-empty `cites` list into the document's
    Elasticsearch child document. Saving the RECAPDocument doesn't do that:
    ES only tracks changes to the document's own fields, not to this
    relation. Documents that had no citations to begin with are left
    alone, ES included.

    :param rd: The RECAPDocument whose citations should be removed.
    :return: None
    """
    # Both kinds of citation come from the same scrubbed text, so drop them
    # together or not at all.
    with transaction.atomic():
        deleted_cited = rd.cited_opinions.all().delete()[0]
        deleted_unmatched = rd.unmatched_citations.all().delete()[0]
    if not (deleted_cited or deleted_unmatched):
        # Nothing changed, so ES has nothing to catch up on. Callers seal
        # whole querysets at a time, so bailing here saves a Celery task
        # and an ES write for every document that had no citations.
        return
    if settings.ELASTICSEARCH_DISABLED:
        # The indexing signals check this too, so honoring it here keeps
        # sealing usable with ES turned off instead of half-indexing.
        return
    update_es_document.delay(
        "ESRECAPDocument",
        ["cites"],
        ("search.RECAPDocument", rd.pk),
        # Losing citations is not something anybody should be alerted
        # about, so don't send the updated document to the percolator.
        skip_percolator_request=True,
    )


def seal_documents(queryset: QuerySet) -> list[str]:
    """Delete a queryset of RECAPDocuments and mark them as sealed.

    :param queryset: A queryset of RECAPDocuments you wish to seal.
    :return: a list of URLs that did not succeed or an empty list if everything
    worked well.
    """
    ia_failures = []
    deleted_filepaths = []
    for i, rd in enumerate(queryset):
        if i > 0:
            # Throttle deletions to avoid overloading archive.org.
            time.sleep(1)

        # Thumbnail
        if rd.thumbnail:
            deleted_filepaths.append(rd.thumbnail.name)
            rd.thumbnail.delete()

        # PDF
        if rd.filepath_local:
            deleted_filepaths.append(rd.filepath_local.name)
            rd.filepath_local.delete()

        # Internet Archive
        if rd.filepath_ia:
            url = rd.filepath_ia
            r = delete_from_ia(url)
            if not r.ok:
                ia_failures.append(url)

        # Clean up other fields and call save()
        # Important to use save() to ensure these changes are updated in ES
        rd.date_upload = None
        rd.is_available = False
        rd.is_sealed = True
        rd.sha1 = ""
        rd.page_count = None
        rd.file_size = None
        rd.ia_upload_failure_count = None
        rd.filepath_ia = ""
        rd.thumbnail_status = THUMBNAIL_STATUSES.NEEDED
        rd.plain_text = ""
        rd.ocr_status = None
        rd.save()

        # Runs after save() so its ES update isn't clobbered by the
        # re-indexing that save() triggers.
        delete_document_citations(rd)

    # Do a CloudFront invalidation
    invalidate_cloudfront([f"/{path}" for path in deleted_filepaths])

    return ia_failures


@retry(
    (botocore.exceptions.HTTPClientError, botocore.exceptions.ConnectionError),
    tries=3,
    delay=1,
    backoff=2,
)
def delete_cluster_files(cluster: OpinionCluster, delete_docket: bool) -> None:
    """Delete the storage files for a cluster about to be sealed.

    Unlike `seal_documents`, this doesn't flag anything as sealed or keep
    the row around — it's meant to run immediately before `seal_cluster`
    hard deletes the cluster (and, if `delete_docket` is set, its docket),
    so the PDFs and other files those rows point at in S3 don't end up
    orphaned. Must be called before the rows are deleted: it reads
    `local_path` etc. off live objects.

    :param cluster: The OpinionCluster about to be deleted.
    :param delete_docket: Whether the cluster's docket will be deleted too,
        and so whether its file should be cleaned up as well.
    :return: None
    """
    deleted_filepaths = []

    for opinion in cluster.sub_opinions.all():
        if not opinion.local_path:
            continue
        path = opinion.local_path.name
        # save=False: the Opinion row is about to be deleted by the
        # caller's cascade anyway, so there's no point writing this
        # change back to a row that won't exist a moment later.
        opinion.local_path.delete(save=False)
        deleted_filepaths.append(path)

    cluster_file_fields = [
        field.name
        for field in OpinionCluster._meta.get_fields()
        if isinstance(field, FileField)
    ]
    for field_name in cluster_file_fields:
        field_file = getattr(cluster, field_name)
        if not field_file:
            continue
        path = field_file.name
        field_file.delete(save=False)
        deleted_filepaths.append(path)

    if delete_docket and cluster.docket.filepath_local:
        path = cluster.docket.filepath_local.name
        cluster.docket.filepath_local.delete(save=False)
        deleted_filepaths.append(path)

    if not deleted_filepaths:
        return

    invalidate_cloudfront([f"/{path}" for path in deleted_filepaths])


# nosemgrep: python.lang.bad-return-outside-function
SEAL_BLOCKERS_MAP = {
    # These prevent cluster deletion
    "favorites.UserTag": lambda cluster: cluster.docket.user_tags,
    "favorites.Note": lambda cluster: cluster.docket.note_set.all().union(
        cluster.note_set.all()
    ),
    "alerts.DocketAlert": lambda cluster: cluster.docket.alerts,
    "visualizations.SCOTUSMap": lambda cluster: SCOTUSMap.objects.filter(
        Q(cluster_start=cluster)
        | Q(cluster_end=cluster)
        | Q(clusters__in=[cluster]),
        deleted=False,
    ),
    # These prevent docket deletion but not cluster deletion
    "audio.Audio": lambda cluster: cluster.docket.audio_files,
    "people_db.AttorneyOrganizationAssociation": lambda cluster: (
        cluster.docket.attorneyorganizationassociation_set
    ),
    "people_db.PartyType": lambda cluster: cluster.docket.party_types,
    "people_db.Role": lambda cluster: cluster.docket.role_set,
    "search.BankruptcyInformation": lambda cluster: getattr(
        cluster.docket, "bankruptcy_information", None
    ),
    "search.Claim": lambda cluster: cluster.docket.claims,
    "search.DocketEntry": lambda cluster: cluster.docket.docket_entries,
    "search.OpinionCluster": lambda cluster: cluster.docket.clusters.exclude(
        pk=cluster.pk
    ),
    "search.SCOTUSDocketEntry": lambda cluster: (
        cluster.docket.scotusdocketentry_set
    ),
    "search.ScotusDocketMetadata": lambda cluster: getattr(
        cluster.docket, "scotus_metadata", None
    ),
    "search.TexasDocketEntry": lambda cluster: (
        cluster.docket.texasdocketentry_set
    ),
    "search.FloridaDocketEntry": lambda cluster: (
        cluster.docket.florida_docket_entries
    ),
    "search.TrialCourtData": lambda cluster: getattr(
        cluster.docket, "trialcourtdata", None
    ),
    "search.CaseTransfer": lambda cluster: CaseTransfer.objects.filter(
        Q(origin_docket=cluster.docket) | Q(destination_docket=cluster.docket)
    ),
}

# Prevent cluster deletion
CLUSTER_BLOCKER_KEYS = [
    "favorites.UserTag",
    "favorites.Note",
    "alerts.DocketAlert",
    "visualizations.SCOTUSMap",
]

# Prevent docket deletion but not cluster deletion
DOCKET_BLOCKER_KEYS = [
    "audio.Audio",
    "people_db.AttorneyOrganizationAssociation",
    "people_db.PartyType",
    "people_db.Role",
    "search.BankruptcyInformation",
    "search.Claim",
    "search.DocketEntry",
    "search.OpinionCluster",
    "search.SCOTUSDocketEntry",
    "search.ScotusDocketMetadata",
    "search.TexasDocketEntry",
    "search.FloridaDocketEntry",
    "search.TrialCourtData",
    "search.CaseTransfer",
]


def check_blocking_relations(cluster: OpinionCluster) -> dict[str, bool]:
    """Check each blocker relation for the given cluster to determine
    if dependent objects exist that block deletion

    :param cluster: OpinionCluster instance to check blockers for
    :return: Dictionary mapping relation keys to boolean indicating presence of blockers
    """
    blockers_found = {}
    for key, get_relation in SEAL_BLOCKERS_MAP.items():
        relation = get_relation(cluster)
        if relation is None:
            blockers_found[key] = False
            continue
        if hasattr(relation, "exists"):
            blockers_found[key] = relation.exists()
        else:
            # For single related objects
            blockers_found[key] = bool(relation)
    return blockers_found


def get_blocking_relations(cluster: OpinionCluster) -> dict[str, Any]:
    """Retrieve the actual blocking related objects for a cluster, annotating
    each with an admin change-url for UI display

    :param cluster: OpinionCluster instance
    :return: Dictionary mapping relation keys to querysets or lists of blocker objects
    """
    blockers = {}
    for key, get_relation in SEAL_BLOCKERS_MAP.items():
        relation = get_relation(cluster)
        if relation:
            qs = relation.all() if hasattr(relation, "all") else [relation]
            for obj in qs:
                # nosemgrep: template.xss.href-django.avoid-variable-in-href
                obj.admin_url = reverse(
                    f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
                    args=[obj.pk],
                )
            blockers[key] = qs
    return blockers


def get_deletion_blockers(cluster: OpinionCluster) -> tuple[bool, bool]:
    """Check whether anything blocks deleting a cluster or its docket

    :param cluster: OpinionCluster to check
    :return: Two-tuple of whether the cluster is blocked from being
        deleted, and whether its docket is
    """
    blockers = check_blocking_relations(cluster)
    return (
        any(blockers.get(key, False) for key in CLUSTER_BLOCKER_KEYS),
        any(blockers.get(key, False) for key in DOCKET_BLOCKER_KEYS),
    )


def seal_cluster(cluster: OpinionCluster, delete_docket: bool) -> None:
    """Delete a cluster and record the redirection that makes its URLs 410

    Callers MUST check `get_deletion_blockers` first: this does no blocker
    checking of its own and will happily delete a cluster that something
    else still points at.

    :param cluster: OpinionCluster to seal
    :param delete_docket: Whether to delete the cluster's docket too
    :return: None
    """
    docket = cluster.docket
    cluster_pk = cluster.pk
    # Must run before the delete() calls below: it reads the file fields
    # off the live rows, and cleans them out of S3 and CloudFront so
    # sealing doesn't leave the PDFs behind for anyone who already has
    # the URL.
    delete_cluster_files(cluster, delete_docket)
    with transaction.atomic():
        cluster.delete()
        ClusterRedirection.objects.create(
            reason=ClusterRedirection.SEALED,
            deleted_cluster_id=cluster_pk,
            cluster=None,
        )
        if delete_docket:
            docket.delete()

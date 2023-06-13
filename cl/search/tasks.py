import socket
from datetime import timedelta

import scorched
from django.apps import apps
from django.conf import settings
from django.utils.timezone import now
from requests import Session
from scorched.exc import SolrError

from cl.celery_init import app
from cl.lib.search_index_utils import InvalidDocumentError
from cl.search.models import Docket, OpinionCluster, RECAPDocument


@app.task
def add_items_to_solr(item_pks, app_label, force_commit=False):
    """Add a list of items to Solr

    :param item_pks: An iterable list of item PKs that you wish to add to Solr.
    :param app_label: The type of item that you are adding.
    :param force_commit: Whether to send a commit to Solr after your addition.
    This is generally not advised and is mostly used for testing.
    """
    search_dicts = []
    model = apps.get_model(app_label)
    items = model.objects.filter(pk__in=item_pks).order_by()
    for item in items:
        try:
            if model in [OpinionCluster, Docket]:
                # Dockets make a list of items; extend, don't append
                search_dicts.extend(item.as_search_list())
            else:
                search_dicts.append(item.as_search_dict())
        except AttributeError as e:
            print(f"AttributeError trying to add: {item}\n  {e}")
        except ValueError as e:
            print(f"ValueError trying to add: {item}\n  {e}")
        except InvalidDocumentError:
            print(f"Unable to parse: {item}")

    with Session() as session:
        si = scorched.SolrInterface(
            settings.SOLR_URLS[app_label], http_connection=session, mode="w"
        )
        try:
            si.add(search_dicts)
            if force_commit:
                si.commit()
        except (socket.error, SolrError) as exc:
            add_items_to_solr.retry(exc=exc, countdown=30)
        else:
            # Mark dockets as updated if needed
            if model == Docket:
                items.update(date_modified=now(), date_last_index=now())


@app.task(ignore_resutls=True)
def add_or_update_recap_docket(
    data, force_commit=False, update_threshold=60 * 60
):
    """Add an entire docket to Solr or update it if it's already there.

    This is an expensive operation because to add or update a RECAP docket in
    Solr means updating every document that's a part of it. So if a docket has
    10,000 documents, we'll have to pull them *all* from the database, and
    re-index them all. It'd be nice to not have to do this, but because Solr is
    de-normalized, every document in the RECAP Solr index has a copy of every
    field in Solr. For example, if the name of the case changes, that has to get
    reflected in every document in the docket in Solr.

    To deal with this mess, we have a field on the docket that says when we last
    updated it in Solr. If that date is after a threshold, we just don't do the
    update unless we know the docket has something new.

    :param data: A dictionary containing the a key for 'docket_pk' and
    'content_updated'. 'docket_pk' will be used to find the docket to modify.
    'content_updated' is a boolean indicating whether the docket must be
    updated.
    :param force_commit: Whether to send a commit to Solr (this is usually not
    needed).
    :param update_threshold: Items staler than this number of seconds will be
    updated. Items fresher than this number will be a no-op.
    """
    if data is None:
        return

    with Session() as session:
        si = scorched.SolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="w"
        )
        some_time_ago = now() - timedelta(seconds=update_threshold)
        d = Docket.objects.get(pk=data["docket_pk"])
        too_fresh = d.date_last_index is not None and (
            d.date_last_index > some_time_ago
        )
        update_not_required = not data.get("content_updated", False)
        if all([too_fresh, update_not_required]):
            return
        else:
            try:
                si.add(d.as_search_list())
                if force_commit:
                    si.commit()
            except SolrError as exc:
                add_or_update_recap_docket.retry(exc=exc, countdown=30)
            else:
                d.date_last_index = now()
                d.save()


@app.task
def add_docket_to_solr_by_rds(item_pks, force_commit=False):
    """Add RECAPDocuments from a single Docket to Solr.

    This is a performance enhancement that can be used when adding many RECAP
    Documents from a single docket to Solr. Instead of pulling the same docket
    metadata for these items over and over (adding potentially thousands of
    queries on a large docket), just pull the metadata once and cache it for
    every document that's added.

    :param item_pks: RECAPDocument pks to add or update in Solr.
    :param force_commit: Whether to send a commit to Solr (this is usually not
    needed).
    :return: None
    """
    with Session() as session:
        si = scorched.SolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="w"
        )
        rds = RECAPDocument.objects.filter(pk__in=item_pks).order_by()
        try:
            metadata = rds[0].get_docket_metadata()
        except IndexError:
            metadata = None

        try:
            si.add(
                [item.as_search_dict(docket_metadata=metadata) for item in rds]
            )
            if force_commit:
                si.commit()
        except SolrError as exc:
            add_docket_to_solr_by_rds.retry(exc=exc, countdown=30)


@app.task
def delete_items(items, app_label, force_commit=False):
    with Session() as session:
        si = scorched.SolrInterface(
            settings.SOLR_URLS[app_label], http_connection=session, mode="w"
        )
        try:
            si.delete_by_ids(list(items))
            if force_commit:
                si.commit()
        except SolrError as exc:
            delete_items.retry(exc=exc, countdown=30)

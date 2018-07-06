from __future__ import print_function

import socket
from datetime import timedelta

import scorched
from django.conf import settings
from django.utils.timezone import now

from cl.audio.models import Audio
from cl.celery import app
from cl.lib.search_index_utils import InvalidDocumentError
from cl.lib.sunburnt import SolrError
from cl.people_db.models import Person
from cl.search.models import Opinion, OpinionCluster, RECAPDocument, Docket


@app.task
def add_or_update_items(items, solr_url=settings.SOLR_OPINION_URL):
    """Adds an item to a solr index.

    This function is for use with the update_index command. It's slightly
    different than the commands below because it expects a Django object,
    rather than a primary key. This rejects the standard Celery advice about
    not passing objects around, but thread safety shouldn't be an issue since
    this is only used by the update_index command, and we want to get the
    objects in the task, not in its caller.
    """
    si = scorched.SolrInterface(solr_url, mode='w')
    if hasattr(items, "items") or not hasattr(items, "__iter__"):
        # If it's a dict or a single item make it a list
        items = [items]
    search_item_list = []
    for item in items:
        try:
            if type(item) == Opinion:
                search_item_list.append(item.as_search_dict())
            elif type(item) == RECAPDocument:
                search_item_list.append(item.as_search_dict())
            elif type(item) == Docket:
                # Slightly different here b/c dockets return a list of search
                # dicts.
                search_item_list.extend(item.as_search_list())
            elif type(item) == Audio:
                search_item_list.append(item.as_search_dict())
            elif type(item) == Person:
                search_item_list.append(item.as_search_dict())
        except AttributeError as e:
            print("AttributeError trying to add: %s\n  %s" % (item, e))
        except ValueError as e:
            print("ValueError trying to add: %s\n  %s" % (item, e))
        except InvalidDocumentError:
            print("Unable to parse: %s" % item)

    try:
        si.add(search_item_list)
    except socket.error as exc:
        add_or_update_items.retry(exc=exc, countdown=120)
    else:
        if type(item) == Docket:
            item.date_last_index = now()
            item.save()


@app.task
def add_or_update_recap_docket(data, force_commit=False,
                               update_threshold=60*60):
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

    si = scorched.SolrInterface(settings.SOLR_RECAP_URL, mode='w')
    some_time_ago = now() - timedelta(seconds=update_threshold)
    d = Docket.objects.get(pk=data['docket_pk'])
    too_fresh = d.date_last_index is not None and \
                      (d.date_last_index > some_time_ago)
    update_not_required = not data.get('content_updated', False)
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
def add_or_update_opinions(item_pks, force_commit=False):
    si = scorched.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                Opinion.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError as exc:
        add_or_update_opinions.retry(exc=exc, countdown=30)


@app.task
def add_or_update_audio_files(item_pks, force_commit=False):
    si = scorched.SolrInterface(settings.SOLR_AUDIO_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                Audio.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError as exc:
        add_or_update_audio_files.retry(exc=exc, countdown=30)


@app.task
def add_or_update_people(item_pks, force_commit=False):
    si = scorched.SolrInterface(settings.SOLR_PEOPLE_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                Person.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError as exc:
        add_or_update_people.retry(exc=exc, countdown=30)


@app.task
def add_or_update_recap_document(item_pks, coalesce_docket=False,
                                 force_commit=False):
    """Add or update recap documents in Solr.

    :param item_pks: RECAPDocument pks to add or update in Solr.
    :param coalesce_docket: If True, assume that the PKs all correspond to
    RECAPDocument objects on the same docket. Instead of processing each
    RECAPDocument individually, pull out repeated metadata so that it is
    only queried from the database once instead of once/RECAPDocument. This can
    provide significant performance improvements since some dockets have
    thousands of entries, each of which would otherwise need to make the same
    queries to the DB.
    :param force_commit: Should we send a commit message at the end of our
    updates?
    :return: None
    """
    si = scorched.SolrInterface(settings.SOLR_RECAP_URL, mode='w')
    rds = RECAPDocument.objects.filter(pk__in=item_pks).order_by()
    if coalesce_docket:
        try:
            metadata = rds[0].get_docket_metadata()
        except IndexError:
            metadata = None
    else:
        metadata = None

    try:
        si.add([item.as_search_dict(docket_metadata=metadata) for item in rds])
        if force_commit:
            si.commit()
    except SolrError as exc:
        add_or_update_recap_document.retry(exc=exc, countdown=30)


@app.task
def delete_items(items, solr_url, force_commit=False):
    si = scorched.SolrInterface(solr_url, mode='w')
    try:
        si.delete_by_ids(list(items))
        if force_commit:
            si.commit()
    except SolrError as exc:
        delete_items.retry(exc=exc, countdown=30)


@app.task
def add_or_update_cluster(pk, force_commit=False):
    si = scorched.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                OpinionCluster.objects.get(pk=pk).sub_opinions.all()])
        if force_commit:
            si.commit()
    except SolrError as exc:
        add_or_update_cluster.retry(exc=exc, countdown=30)

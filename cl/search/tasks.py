import scorched
import socket

from django.conf import settings

from cl.audio.models import Audio
from cl.celery import app
from cl.lib.search_index_utils import InvalidDocumentError
from cl.lib.sunburnt import SolrError
from cl.people_db.models import Person
from cl.search.models import Opinion, OpinionCluster, RECAPDocument


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
            if type(item) == Audio:
                search_item_list.append(item.as_search_dict())
            elif type(item) == Opinion:
                search_item_list.append(item.as_search_dict())
            elif type(item) == RECAPDocument:
                search_item_list.append(item.as_search_dict())
            elif type(item) == Person:
                search_item_list.append(item.as_search_dict())
        except AttributeError as e:
            print "AttributeError trying to add: %s\n  %s" % (item, e)
        except ValueError as e:
            print "ValueError trying to add: %s\n  %s" % (item, e)
        except InvalidDocumentError:
            print "Unable to parse: %s" % item

    try:
        si.add(search_item_list)
    except socket.error, exc:
        add_or_update_items.retry(exc=exc, countdown=120)


@app.task
def add_or_update_opinions(item_pks, force_commit=True):
    si = scorched.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                Opinion.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_opinions.retry(exc=exc, countdown=30)


@app.task
def add_or_update_audio_files(item_pks, force_commit=True):
    si = scorched.SolrInterface(settings.SOLR_AUDIO_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                Audio.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_audio_files.retry(exc=exc, countdown=30)


@app.task
def add_or_update_people(item_pks, force_commit=True):
    si = scorched.SolrInterface(settings.SOLR_PEOPLE_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                Person.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_people.retry(exc=exc, countdown=30)


@app.task
def add_or_update_recap_document(item_pks, force_commit=True):
    si = scorched.SolrInterface(settings.SOLR_RECAP_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                RECAPDocument.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_recap_document.retry(exc=exc, countdown=30)


@app.task
def delete_items(items, solr_url, force_commit=False):
    si = scorched.SolrInterface(solr_url, mode='w')
    try:
        si.delete_by_ids(list(items))
        if force_commit:
            si.commit()
    except SolrError, exc:
        delete_items.retry(exc=exc, countdown=30)


@app.task
def add_or_update_cluster(pk, force_commit=True):
    si = scorched.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    try:
        si.add([item.as_search_dict() for item in
                OpinionCluster.objects.get(pk=pk).sub_opinions.all()])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_cluster.retry(exc=exc, countdown=30)

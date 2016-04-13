import socket

from cl.audio.models import Audio
from cl.celery import app
from cl.lib.sunburnt import SolrError
from cl.lib import sunburnt
from cl.people_db.models import Person
from cl.search.models import Opinion, OpinionCluster, Docket
from cl.search.search_indexes import (
    InvalidDocumentError, SearchAudioFile, SearchDocument, SearchPerson,
    SearchDocketFile,
)


from django.conf import settings


@app.task
def add_or_update_items(items, solr_url=settings.SOLR_OPINION_URL):
    """Adds an item to a solr index.

    This function is for use with the update_index command. It's slightly
    different than the commands below because it expects a Django object,
    rather than a primary key. This rejects the standard Celery advice about
    not passing objects around, but thread safety shouldn't be an issue since
    this is only used by the update_index command, and we want to query and
    build the SearchDocument objects in the task, not in its caller.
    """
    si = sunburnt.SolrInterface(solr_url, mode='w')
    if hasattr(items, "items") or not hasattr(items, "__iter__"):
        # If it's a dict or a single item make it a list
        items = [items]
    search_item_list = []
    for item in items:
        try:
            if type(item) == Audio:
                search_item_list.append(SearchAudioFile(item))
            elif type(item) == Opinion:
                search_item_list.append(SearchDocument(item))
            elif type(item) == Docket:
                search_item_list.append(SearchDocketFile(item))
            elif type(item) == Person:
                search_item_list.append(SearchPerson(item))
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
    si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    try:
        si.add([SearchDocument(item) for item in
                Opinion.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_opinions.retry(exc=exc, countdown=30)


@app.task
def add_or_update_audio_files(item_pks, force_commit=True):
    si = sunburnt.SolrInterface(settings.SOLR_AUDIO_URL, mode='w')
    try:
        si.add([SearchAudioFile(item) for item in
                Audio.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_audio_files.retry(exc=exc, countdown=30)


@app.task
def add_or_update_people(item_pks, force_commit=True):
    si = sunburnt.SolrInterface(settings.SOLR_PEOPLE_URL, mode='w')
    try:
        si.add([SearchPerson(item) for item in
                Person.objects.filter(pk__in=item_pks)])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_people.retry(exc=exc, countdown=30)

@app.task
def delete_items(items, solr_url):
    si = sunburnt.SolrInterface(solr_url, mode='w')
    si.delete(list(items))
    si.commit()


@app.task
def add_or_update_cluster(pk, force_commit=True):
    si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    try:
        si.add([SearchDocument(item) for item in
                OpinionCluster.objects.get(pk=pk).sub_opinions.all()])
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_cluster.retry(exc=exc, countdown=30)


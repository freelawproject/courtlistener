import os
import socket
import sys
from alert.lib.sunburnt import SolrError
from audio.models import Audio

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
from django.conf import settings

from alert.lib import sunburnt
from alert.search.models import Citation
from alert.search.models import Document
from alert.search.search_indexes import InvalidDocumentError, SearchAudioFile
from alert.search.search_indexes import SearchDocument
from celery import task


@task
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
            elif type(item) == Document:
                search_item_list.append(SearchDocument(item))
        except AttributeError:
            print "AttributeError trying to add doc.pk: %s" % item.pk
        except InvalidDocumentError:
            print "Unable to parse document %s" % item.pk

    try:
        si.add(search_item_list)
    except socket.error, exc:
        add_or_update_items.retry(exc=exc, countdown=120)

@task
def delete_items(items):
    si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    si.delete(list(items))
    si.commit()

@task
def add_or_update_docs(item_pks):
    si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    item_list = []
    for pk in item_pks:
        item = Document.objects.get(pk=pk)
        item_list.append(SearchDocument(item))
    si.add(item_list)
    si.commit()

@task
def add_or_update_audio_files(item_pks):
    si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    item_list = []
    for pk in item_pks:
        item = Audio.objects.get(pk=pk)
        item_list.append(SearchDocument(item))
    si.add(item_list)
    si.commit()

@task
def delete_item(pk, solr_url):
    """Deletes the item from the index.
    """
    si = sunburnt.SolrInterface(solr_url, mode='w')
    si.delete(pk)
    si.commit()

@task
def add_or_update_doc(pk, force_commit=True):
    """Updates the document in the index. Called by Document save function.
    """
    si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    try:
        si.add(SearchDocument(Document.objects.get(pk=pk)))
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_doc.retry(exc=exc, countdown=30)

@task
def add_or_update_audio_file(pk, force_commit=True):
    """Updates the document in the index. Called by Document save function.
    """
    si = sunburnt.SolrInterface(settings.SOLR_AUDIO_URL, mode='w')
    try:
        si.add(SearchAudioFile(Audio.objects.get(pk=pk)))
        if force_commit:
            si.commit()
    except SolrError, exc:
        add_or_update_audio_file.retry(exc=exc, countdown=30)


@task
def update_cite(citation_id, force_commit=False):
    """If a citation and a document are both updated simultaneously, we will
    needlessly update the index twice. No easy way around it.
    """
    si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='w')
    cite = Citation.objects.get(pk=citation_id)
    for doc in cite.parent_documents.all():
        search_doc = SearchDocument(doc)
        si.add(search_doc)
    if force_commit:
        si.commit()

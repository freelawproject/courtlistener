import socket
import sys
execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)

from alert import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.lib import sunburnt
from alert.search.models import Citation
from alert.search.models import Document
from alert.search.search_indexes import InvalidDocumentError
from alert.search.search_indexes import SearchDocument
from celery.decorators import task
from alert.lib.db_tools import queryset_generator

class LocalDocument(object):
    """Convenience class which save the field from database temporarily.
    After the iterations of pagerank calculation, it will upload the pagerank
    to database. This will avoid frequent hit of database.
    """
    def __init__(self, id, cases_cited_count, citing_cases_id, pagerank=1):
        self.id = id
        self.cases_cited_count = cases_cited_count
        self.citing_cases_id = citing_cases_id
        self.pagerank = pagerank

@task
def add_or_update_doc_object(doc, solr_url=settings.SOLR_URL):
    """Adds a document object to the solr index.

    This function is for use with the update_index command. It's slightly
    different than the commands below because it expects a Django object,
    rather than a primary key. This rejects the standard Celery advice about
    not passing objects around, but thread safety shouldn't be an issue since
    this is only used by the update_index command, and we want to query and
    build the SearchDocument objects in the task, not in its caller.
    """
    si = sunburnt.SolrInterface(solr_url, mode='w')
    try:
        search_doc = SearchDocument(doc)
        si.add(search_doc)
    except AttributeError:
        print "AttributeError trying to add doc.pk: %s" % doc.pk
    except InvalidDocumentError:
        print "Unable to parse document %s" % doc.pk
    except socket.error, exc:
        add_or_update_doc_object.retry(exc=exc, countdown=120)

@task
def delete_docs(docs):
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    si.delete(list(docs))
    si.commit()

@task
def add_or_update_docs(docs):
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    for doc in docs:
        doc = Document.objects.get(pk=doc)
        search_doc = SearchDocument(doc)
        si.add(search_doc)
        si.commit()

@task
def delete_doc(document_id):
    """Deletes the document from the index.

    Called by Document delete function and from models.py when an item is deleted.

    Note that putting a line like...

      if document_id is not None:

    ...will mean that models.py deletions won't work. We've had a bug with that in
    the past, so exercise caution when tweaking this function.
    """
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    si.delete(document_id)
    si.commit()

@task
def add_or_update_doc(document_id):
    """Updates the document in the index. Called by Document save function.
    """
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    doc = Document.objects.get(pk=document_id)
    search_doc = SearchDocument(doc)
    si.add(search_doc)
    si.commit()

@task
def update_cite(citation_id):
    """If a citation and a document are both updated simultaneously, we will
    needlessly update the index twice. No easy way around it.
    """
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    cite = Citation.objects.get(pk=citation_id)
    for doc in cite.document_set.all():
        search_doc = SearchDocument(doc)
        si.add(search_doc)
    si.commit()

@task
def do_pagerank():
    DAMPING_FACTOR = 0.85
    MAX_ITERATIONS = 100
    MIN_DELTA = 0.00001

    #graph_size = Document.objects.all().count()
    min_value = (1.0 - DAMPING_FACTOR)
    locdoc_dict = dict()
    case_list = queryset_generator(Document.objects.all())
    for case in case_list:
        id = case.pk
        cases_cited_count = len(case.cases_cited.all())
        citing_cases_id = []
        for citing_case in case.citation.citing_cases.all():
            citing_cases_id.append(citing_case.pk)
        locdoc = LocalDocument(id, cases_cited_count, citing_cases_id)
        locdoc_dict[id] = locdoc

    for i in range(MAX_ITERATIONS):
        diff = 0
        print("No.{:d} iteration...({:d} times at most)".format(i, MAX_ITERATIONS))
        for key, locdoc in locdoc_dict.iteritems():
            tmp_pagerank = min_value
            for id in locdoc.citing_cases_id:
                citing_case = locdoc_dict[id]
                tmp_pagerank += DAMPING_FACTOR * citing_case.pagerank / citing_case.cases_cited_count
            diff += abs(locdoc.pagerank - tmp_pagerank)
            locdoc.pagerank = tmp_pagerank
        if diff < MIN_DELTA:
            break

    print('Updating database...')
    case_list = queryset_generator(Document.objects.all())
    for case in case_list:
        case.pagerank = locdoc_dict[case.pk].pagerank
        case.save(index=False)
        #print(str(case.pk)+":\t"+str(case.pagerank))
    print('PageRank calculation finish!')
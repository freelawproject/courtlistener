# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import socket
import sys
sys.path.append('/var/www/court-listener/alert')

from alert import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.lib import sunburnt
from alert.search.models import Citation
from alert.search.models import Document
from alert.search.search_indexes import InvalidDocumentError
from alert.search.search_indexes import SearchDocument
from celery.decorators import task

si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')

@task
def add_or_update_doc_object(doc):
    '''Adds a document object to the solr index.
    
    This function is for use with the update_index command. It's slightly 
    different than the commands below because it expects a Django object, 
    rather than a primary key. This rejects the standard Celery advice about
    not passing objects around, but thread safety shouldn't be an issue since
    this is only used by the update_index command, and we want to query and 
    build the SearchDocument objects in the task, not in its caller.'''
    retries = 0
    while True:
        try:
            search_doc = SearchDocument(doc)
            si.add(search_doc)
            return 0
        except InvalidDocumentError:
            print "Unable to parse document %s" % doc.pk
            break
        except socket.error:
            # Try again if we haven't tried ten times yet
            if retries == 10:
                print "Document %s was unable to be indexed due to %d socket errors." % (doc.pk, retries)
                break
            retries += 1
            continue

@task
def delete_docs(docs):
    si.delete(list(docs))
    si.commit()

@task
def add_or_update_docs(docs):
    for doc in docs:
        doc = Document.objects.get(pk=doc)
        search_doc = SearchDocument(doc)
        si.add(search_doc)
        si.commit()

@task
def delete_doc_handler(sender, **kwargs):
    '''Responds to the post_delete signal and deletes the document from the 
    index. See search/__init__.py for the connecting code.
    '''
    si.delete(kwargs['instance'].pk)
    si.commit()

@task
def save_doc_handler(sender, **kwargs):
    '''Responds to the post_save signal and updates the document in the search
    index. See search/__init__.py for the connecting code.
    '''
    doc = Document.objects.get(pk=kwargs['instance'].pk)
    search_doc = SearchDocument(doc)
    si.add(search_doc)
    si.commit()

@task
def save_cite_handler(sender, **kwargs):
    '''If a citation is updated, we should update the index. If a citation and
    a document are both updated simultaneously, we will needlessly update the
    index twice. No easy way around it.
    '''
    if not kwargs['created']:
        # We only do this on update, not creation.
        cite = Citation.objects.get(pk=kwargs['instance'].pk)
        docs = Document.objects.filter(citation=cite)
        for doc in docs:
            search_doc = SearchDocument(doc)
            si.add(search_doc)
        si.commit()

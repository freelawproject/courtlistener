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

from datetime import datetime
from datetime import time
from django.core.urlresolvers import NoReverseMatch
from django.template import Context
from django.template import loader

class InvalidDocumentError(Exception):
    "The document could not be formed"
    pass

class SearchDocument(object):
    def __init__(self, doc):
        # Used to nuke null and control characters.
        null_map = dict.fromkeys(range(0, 10) + range(11, 13) + range(14, 32))

        # Standard fields
        self.id = doc.pk
        print "Django DB value for dateFiled: %s" % doc.dateFiled
        if doc.dateFiled is not None:
            self.dateFiled = datetime.combine(doc.dateFiled, time())
        self.court = doc.court.short_name
        self.court_id = doc.court.courtUUID
        self.court_citation_string = doc.court.citation_string
        try:
            self.caseName = doc.citation.caseNameFull
            self.absolute_url = doc.get_absolute_url()
        except AttributeError, NoReverseMatch:
            raise InvalidDocumentError
        self.docketNumber = doc.citation.docketNumber
        self.westCite = doc.citation.westCite
        self.lexisCite = doc.citation.lexisCite
        self.status = doc.get_documentType_display()
        self.source = doc.source
        self.download_url = doc.download_URL
        self.local_path = str(doc.local_path)

        # Load the caseName field using a template to make it a concatenation
        case_name_template = loader.get_template('search/indexes/caseNumber.txt')
        c = Context({ 'object': doc })
        self.caseNumber = case_name_template.render(c)

        # Load the document text using a template for cleanup and concatenation
        text_template = loader.get_template('search/indexes/text.txt')
        c = Context({ 'object': doc })
        self.text = text_template.render(c).translate(null_map)

        # Faceting fields
        self.status_exact = doc.get_documentType_display()
        self.court_exact = doc.court.courtUUID

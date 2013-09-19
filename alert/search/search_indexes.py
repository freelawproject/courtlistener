from datetime import datetime
from datetime import time
from django.core.urlresolvers import NoReverseMatch
from django.template import Context
from django.template import loader
from alert.casepage.views import make_caption, make_citation_string


class InvalidDocumentError(Exception):
    """The document could not be formed"""
    def __init__(self, message):
        Exception.__init__(self, message)


class SearchDocument(object):
    def __init__(self, doc):
        # Used to nuke null and control characters.
        null_map = dict.fromkeys(range(0, 10) + range(11, 13) + range(14, 32))

        # Standard fields
        self.id = doc.pk
        if doc.date_filed is not None:
            self.dateFiled = datetime.combine(doc.date_filed, time())
        self.citeCount = doc.citation_count
        self.court = doc.court.short_name
        self.court_id = doc.court.courtUUID
        self.court_citation_string = doc.court.citation_string
        try:
            self.caseName = doc.citation.case_name
            self.absolute_url = doc.get_absolute_url()
        except AttributeError:
            raise InvalidDocumentError("Unable to save to index due to missing Citation object.")
        except NoReverseMatch:
            raise InvalidDocumentError("Unable to save to index due to missing absolute_url.")
        self.judge = doc.judges
        self.suitNature = doc.nature_of_suit
        self.docketNumber = doc.citation.docket_number
        self.lexisCite = doc.citation.lexis_cite
        self.neutralCite = doc.citation.neutral_cite
        self.status = doc.get_precedential_status_display()
        self.source = doc.source
        self.download_url = doc.download_URL
        self.local_path = unicode(doc.local_path)
        self.citation = make_citation_string(doc)
        # Assign the docket number and/or the citation to the caseNumber field
        if doc.citation and doc.citation.docket_number:
            self.caseNumber = '%s, %s' % (self.citation, doc.citation.docket_number)
        elif doc.citation:
            self.caseNumber = self.citation
        elif doc.citation.docket_number:
            self.caseNumber = self.citation.docket_number

        # Load the document text using a template for cleanup and concatenation
        text_template = loader.get_template('search/indexes/text.txt')
        c = Context({'object': doc})
        self.text = '%s %s' % (text_template.render(c).translate(null_map), self.caseNumber)

        # Faceting fields
        self.status_exact = doc.get_precedential_status_display()
        self.court_exact = doc.court.courtUUID

from datetime import datetime
from datetime import time
from django.core.urlresolvers import NoReverseMatch
from django.template import Context
from django.template import loader


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
            raise InvalidDocumentError("Unable to save to index due to missing absolute url.")
        self.judge = doc.judges
        self.suitNature = doc.nature_of_suit
        self.docketNumber = doc.citation.docket_number
        self.westCite = "%s %s" % (doc.citation.west_cite, doc.citation.west_state_cite)
        self.lexisCite = doc.citation.lexis_cite
        self.neutralCite = doc.citation.neutral_cite
        self.status = doc.get_precedential_status_display()
        self.source = doc.source
        self.download_url = doc.download_URL
        self.local_path = unicode(doc.local_path)

        # Load the case_name field using a template to make it a concatenation
        case_name_template = loader.get_template('search/indexes/caseNumber.txt')
        c = Context({'object': doc})
        self.caseNumber = case_name_template.render(c)

        # Load the document text using a template for cleanup and concatenation
        text_template = loader.get_template('search/indexes/text.txt')
        c = Context({'object': doc})
        self.text = text_template.render(c).translate(null_map)

        # Faceting fields
        self.status_exact = doc.get_precedential_status_display()
        self.court_exact = doc.court.courtUUID

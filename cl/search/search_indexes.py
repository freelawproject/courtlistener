from datetime import datetime
from datetime import time
from django.core.urlresolvers import NoReverseMatch
from django.template import loader
from cl.opinion_page.views import make_citation_string


class InvalidDocumentError(Exception):
    """The document could not be formed"""
    def __init__(self, message):
        Exception.__init__(self, message)


# Used to nuke null and control characters.
null_map = dict.fromkeys(range(0, 10) + range(11, 13) + range(14, 32))


class SearchDocument(object):
    def __init__(self, item):
        # Standard fields
        self.id = item.pk
        if item.date_filed is not None:
            self.dateFiled = datetime.combine(item.date_filed, time())  # Midnight, PST
        self.citeCount = item.citation_count
        self.court = item.docket.court.full_name
        self.court_id = item.docket.court.pk
        self.court_citation_string = item.docket.court.citation_string
        try:
            self.caseName = item.case_name
            self.absolute_url = item.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url "
                "(court_id: %s, item.pk: %s). Might the court have in_use set "
                "to False?" % (self.docket.court_id, item.pk)
            )
        self.judge = item.judges
        self.suitNature = item.nature_of_suit
        self.docketNumber = item.docket.docket_number
        self.lexisCite = item.lexis_cite
        self.neutralCite = item.neutral_cite
        self.status = item.get_precedential_status_display()
        self.source = item.source
        self.download_url = item.download_url
        self.local_path = unicode(item.local_path)
        self.citation = make_citation_string(item)
        # Assign the docket number and/or the citation to the caseNumber field
        if item.citation and item.docket.docket_number:
            self.caseNumber = '%s, %s' % (self.citation, item.docket.docket_number)
        elif item.citation:
            self.caseNumber = self.citation
        elif item.docket.docket_number:
            self.caseNumber = item.docket.docket_number

        # Load the document text using a template for cleanup and concatenation
        text_template = loader.get_template('search/indexes/opinion_text.txt')
        context = {'object': item}
        self.text = '%s %s' % (
            text_template.render(context).translate(null_map),
            self.caseNumber
        )

        # Faceting fields
        self.status_exact = item.get_precedential_status_display()
        self.court_exact = item.docket.court.pk


class SearchAudioFile(object):
    def __init__(self, item):
        self.id = item.pk
        self.docket = item.docket_id
        if item.docket.date_argued is not None:
            self.dateArgued = datetime.combine(item.docket.date_argued, time())  # Midnight, PST
        self.court = item.docket.court.full_name
        self.court_id = item.docket.court_id
        self.court_citation_string = item.docket.court.citation_string
        self.court_exact = item.docket.court_id  # For faceting
        self.caseName = item.case_name
        try:
            self.absolute_url = item.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url: %s"
                % item.pk)
        self.judge = item.judges
        self.docketNumber = item.docket.docket_number
        self.file_size_mp3 = item.local_path_mp3.size
        self.duration = item.duration
        self.source = item.source
        self.download_url = item.download_url
        self.local_path = unicode(item.local_path_mp3)

        text_template = loader.get_template('search/indexes/audio_text.txt')
        context = {'object': item}
        self.text = text_template.render(context).translate(null_map)

from cl.lib.utils import deepgetattr

from datetime import datetime
from datetime import time
from django.core.urlresolvers import NoReverseMatch
from django.template import loader


class InvalidDocumentError(Exception):
    """The document could not be formed"""
    def __init__(self, message):
        Exception.__init__(self, message)


# Used to nuke null and control characters.
null_map = dict.fromkeys(range(0, 10) + range(11, 13) + range(14, 32))


class SearchDocument(object):
    def __init__(self, item):
        self.id = item.pk
        self.docket_id = item.cluster.docket.pk
        self.cluster_id = item.cluster.pk
        self.court_id = item.cluster.docket.court.pk

        # Docket
        if item.cluster.docket.date_argued is not None:
            self.dateArgued = datetime.combine(
                item.cluster.docket.date_argued,
                time(),
            )
        if item.cluster.docket.date_reargued is not None:
            self.dateReargued = datetime.combine(
                item.cluster.docket.date_reargued,
                time(),
            )
        if item.cluster.docket.date_reargument_denied is not None:
            self.dateReargumentDenied = datetime.combine(
                item.cluster.docket.date_reargument_denied,
                time(),
            )
        self.docketNumber = item.cluster.docket.docket_number

        # Court
        self.court = item.cluster.docket.court.full_name
        self.court_citation_string = item.cluster.docket.court.citation_string

        # Cluster
        if item.cluster.case_name:
            self.caseName = item.cluster.case_name
        elif item.cluster.case_name_full:
            self.caseName = item.cluster.case_name_full
        self.sibling_ids = [sibling.pk for sibling in item.siblings.all()]
        self.panel_ids = [judge.pk for judge in item.cluster.panel.all()]
        self.non_participating_judge_ids = [judge.pk for judge in
                                            item.cluster.non_participating_judges.all()]
        self.judge = item.cluster.judges
        self.per_curiam = item.cluster.per_curiam
        if item.cluster.date_filed is not None:
            self.dateFiled = datetime.combine(
                item.cluster.date_filed,
                time()
            )  # Midnight, PST
        self.lexisCite = item.cluster.lexis_cite
        self.citation = item.cluster.citation_string
        self.neutralCite = item.cluster.neutral_cite
        self.scdb_id = item.cluster.supreme_court_db_id
        self.source = item.cluster.source
        self.attorney = item.cluster.attorneys
        self.suitNature = item.cluster.nature_of_suit
        self.citeCount = item.cluster.citation_count
        self.status = item.cluster.get_precedential_status_display()

        # Opinion
        self.cites = [opinion.pk for opinion in item.opinions_cited.all()]
        self.author_id = getattr(item.author, 'pk', None)
        self.joined_by_ids = [judge.pk for judge in item.joined_by.all()]
        self.type = item.type
        self.download_url = item.download_url or None
        self.local_path = unicode(item.local_path)

        try:
            self.absolute_url = item.cluster.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url "
                "(court_id: %s, item.pk: %s). Might the court have in_use set "
                "to False?" % (self.docket.court_id, item.pk)
            )

        # Load the document text using a template for cleanup and concatenation
        text_template = loader.get_template('indexes/opinion_text.txt')
        context = {'item': item, 'citation_string': self.citation}
        self.text = text_template.render(context).translate(null_map)

        # Faceting fields
        self.status_exact = item.cluster.get_precedential_status_display()
        self.court_exact = item.cluster.docket.court.pk


class SearchAudioFile(object):
    def __init__(self, item):
        self.id = item.pk
        self.docket_id = item.docket_id

        # Docket
        if item.docket.date_argued is not None:
            self.dateArgued = datetime.combine(
                item.docket.date_argued,
                time()
            )
        if item.docket.date_reargued is not None:
            self.dateReargued = datetime.combine(
                item.docket.date_reargued,
                time()
            )
        if item.docket.date_reargument_denied is not None:
            self.dateReargumentDenied = datetime.combine(
                item.docket.date_reargument_denied,
                time()
            )
        self.docketNumber = item.docket.docket_number

        # Court
        self.court = item.docket.court.full_name
        self.court_id = item.docket.court_id
        self.court_citation_string = item.docket.court.citation_string

        # Audio file
        if item.case_name:
            self.caseName = item.case_name
        else:
            self.caseName = item.case_name_full
        self.panel_ids = [judge.pk for judge in item.panel.all()]
        self.judge = item.judges
        self.file_size_mp3 = deepgetattr(item, 'local_path_mp3.size', None)
        self.duration = item.duration
        self.source = item.source
        self.download_url = item.download_url
        self.local_path = unicode(getattr(item, 'local_path_mp3', None))

        try:
            self.absolute_url = item.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url: %s"
                % item.pk)

        text_template = loader.get_template('indexes/audio_text.txt')
        context = {'item': item}
        self.text = text_template.render(context).translate(null_map)

        # For faceting
        self.court_exact = item.docket.court_id

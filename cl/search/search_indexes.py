from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.utils import deepgetattr
from cl.search.models import DocketEntry

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
        self.caseName = best_case_name(item.cluster)
        self.caseNameShort = item.cluster.case_name_short
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
        self.citation = [cite for cite in
                         item.cluster.citation_list if cite]  # Nuke '' and None
        self.neutralCite = item.cluster.neutral_cite
        self.scdb_id = item.cluster.scdb_id
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
        context = {'item': item, 'citation_string': item.cluster.citation_string}
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
        self.caseName = best_case_name(item)
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

class SearchDocketFile(object):

    def __init__(self, item):
        self.id = item.pk
        self.court_id = item.court.pk
        # Docket
        if item.date_argued is not None:
            self.dateArgued = datetime.combine(
                item.date_argued,
                time()
            )
        if item.date_reargued is not None:
            self.dateReargued = datetime.combine(
                item.date_reargued,
                time()
            )
        if item.date_reargument_denied is not None:
            self.dateReargumentDenied = datetime.combine(
                item.date_reargument_denied,
                time()
            )
        if item.date_filed is not None:
            self.dateFiled = datetime.combine(
                item.date_filed,
                time()
            )
        self.docketNumber = item.docket_number
        self.caseName = item.case_name
        self.pacerCaseId = item.pacer_case_id
        self.court = item.court.full_name
        if item.nature_of_suit is not None:
            self.natureOfSuit = item.nature_of_suit
        if item.cause is not None:
            self.cause = item.cause
        if item.jury_demand is not None:
            self.juryDemand = item.jury_demand
        if item.jurisdiction_type is not None:
            self.jurisdictionType = item.jurisdiction_type
        # Judge the docket is assigned to
        if item.assigned_to is not None:
            self.assignedTo = item.assigned_to.name_full

        # Getting all the DocketEntries of the docket.
        docket_entries = DocketEntry.objects.filter(docket=item)
        text_template = loader.get_template('indexes/dockets_text.txt')
        # Docket Entries are extracted in the template.
        context = {'item': item, 'docket_entries_seq' : docket_entries}

        self.docketEntries = text_template.render(context).translate(null_map)



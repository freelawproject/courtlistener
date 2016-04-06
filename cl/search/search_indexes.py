from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.utils import deepgetattr
from cl.search.models import DocketEntry

from datetime import datetime, date, time
from django.core.urlresolvers import NoReverseMatch
from django.template import loader


def solr_list(m2m_list, field):
    new_list = []
    for obj in m2m_list:
        obj = getattr(obj, field)
        if obj is None:
            continue
        if isinstance(obj, date):
            obj = datetime.combine(obj, time())
        new_list.append(obj)
    return new_list


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


class SearchPerson(object):
    def __init__(self, item):
        self.id = item.pk
        self.fjc_id = item.fjc_id
        self.cl_id = item.cl_id
        self.alias_ids = [alias.pk for alias in item.aliases.all()]
        self.races = [r.get_race_display() for r in item.race.all()]
        self.gender = item.get_gender_display()
        self.religion = item.get_religion_display()
        self.name = item.name_full
        self.name_reverse = item.name_full_reverse
        if item.date_dob is not None:
            self.dob = datetime.combine(item.date_dob, time())
        self.date_granularity_dob = item.date_granularity_dob
        if item.date_dod is not None:
            self.dod = datetime.combine(item.date_dod, time())
        self.date_granularity_dod = item.date_granularity_dod
        self.dob_city = item.dob_city
        self.dob_state = item.get_dob_state_display()
        self.absolute_url = item.get_absolute_url()

        # Joined Values. Brace yourself.
        positions = item.positions.all()
        if positions.count() > 0:
            self.court_id = [p.court.pk for p in positions if
                             p.court is not None]
            self.position_type = [p.get_position_type_display() for p in positions]
            self.appointer = [p.appointer.name_full for p in positions
                              if p.appointer is not None]
            self.supervisor = [p.supervisor.name_full for p in positions
                               if p.supervisor is not None]
            self.predecessor = [p.predecessor.name_full for p in positions
                                if p.predecessor is not None]

            self.date_nominated = solr_list(positions, 'date_nominated')
            self.date_elected = solr_list(positions, 'date_elected')
            self.date_recess_appointment = solr_list(
                positions, 'date_recess_appointment',
            )
            self.date_referred_to_judicial_committee = solr_list(
                positions, 'date_referred_to_judicial_committee',
            )
            self.date_judicial_committee_action =solr_list(
                positions, 'date_judicial_committee_action',
            )
            self.date_hearing = solr_list(positions, 'date_hearing')
            self.date_confirmation = solr_list(positions, 'date_confirmation')
            self.date_start = solr_list(positions, 'date_start')
            self.date_granularity_start = solr_list(
                positions, 'date_granularity_start',
            )
            self.date_retirement = solr_list(
                positions, 'date_retirement',
            )
            self.date_termination = solr_list(
                positions, 'date_termination',
            )
            self.date_granularity_termination = solr_list(
                positions, 'date_granularity_termination',
            )
            self.judicial_committee_action = [
                p.get_judicial_committee_action_display() for p in positions if
                p.judicial_committee_action is not None
            ]
            self.nomination_process = [
                p.get_nomination_process_display() for p in positions if
                p.nomination_process is not None
            ]
            self.selection_method = [
                p.get_how_selected_display() for p in positions if
                p.how_selected is not None
            ]
            self.termination_reason = [
                p.get_termination_reason_display() for p in positions if
                p.termination_reason is not None
            ]

        self.school = [e.school.name for e in item.educations.all()]

        self.political_affiliation = [
            pa.get_political_party_display() for pa in
            item.political_affiliations.all() if pa is not None
        ]

        self.aba_rating = [
            r.get_rating_display() for r in item.aba_ratings.all() if
            r is not None
        ]

        text_template = loader.get_template('indexes/person_text.txt')
        context = {'item': item}
        self.text = text_template.render(context).translate(null_map)

        # For faceting
        self.court_exact = [p.court.pk for p in positions if p.court is not None]



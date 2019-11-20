# Solr fields that are used for highlighting or other output in the search
# results
SOLR_OPINION_HL_FIELDS = [
    'caseName',
    'citation',
    'court_citation_string',
    'docketNumber',
    'judge',
    'lexisCite',
    'neutralCite',
    'suitNature',
    'text'
]
SOLR_RECAP_HL_FIELDS = [
    'assignedTo',
    'caseName',
    'cause',
    'court_citation_string',
    'docketNumber',
    'juryDemand',
    'referredTo',
    'short_description',
    'suitNature',
    'text'
]
SOLR_AUDIO_HL_FIELDS = [
    'text',
    'caseName',
    'judge',
    'docketNumber',
    'court_citation_string'
]
SOLR_PEOPLE_HL_FIELDS = [
    'name',
    'dob_city',
    'dob_state',
    'name_reverse'
]

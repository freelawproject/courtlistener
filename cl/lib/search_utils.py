import re
from urllib import urlencode
from urlparse import parse_qs

from django.conf import settings

from cl.citations.find_citations import get_citations
from cl.citations.match_citations import match_citation
from cl.recommendations.search import handle_related_query
from cl.search.models import Court

boosts = {
    'qf': {
        'o': {
            'text': 1,
            'caseName': 4,
            'docketNumber': 2,
        },
        'r': {
            'text': 1,
            'caseName': 4,
            'docketNumber': 3,
            'description': 2,
        },
        'oa': {
            'text': 1,
            'caseName': 4,
            'docketNumber': 2,
        },
        'p': {
            'text': 1,
            'name': 4,
            # Suppress these fields b/c a match on them returns the wrong
            # person.
            'appointer': 0.3,
            'supervisor': 0.3,
            'predecessor': 0.3,
        },
    },
    # Phrase-based boosts.
    'pf': {
        'o': {
            'text': 3,
            'caseName': 3,
        },
        'r': {
            'text': 3,
            'caseName': 3,
            'description': 3,
        },
        'oa': {
            'caseName': 3,
        },
        'p': {
            # None here. Phrases don't make much sense for people.
        },
    },
}


def make_get_string(request, nuke_fields=None):
    """Makes a get string from the request object. If necessary, it removes
    the pagination parameters.
    """
    if nuke_fields is None:
        nuke_fields = ['page']
    get_dict = parse_qs(request.META['QUERY_STRING'])
    for key in nuke_fields:
        try:
            del get_dict[key]
        except KeyError:
            pass
    get_string = urlencode(get_dict, True)
    if len(get_string) > 0:
        get_string += '&'
    return get_string


def get_string_to_dict(get_string):
    """Reverses the work that the make_get_string function performs, building a
    dict from the get_string.

    Used by alerts.
    """
    get_dict = {}
    for k, v in parse_qs(get_string).items():
        get_dict[k] = v[0]
    return get_dict


def get_query_citation(cd):
    """Extract citations from the query string and return them, or return
    None
    """
    if not cd.get('q'):
        return None
    citations = get_citations(cd['q'], html=False)

    matches = None
    if len(citations) == 1:
        # If it's not exactly one match, user doesn't get special help.
        matches = match_citation(citations[0])
        if len(matches) >= 1:
            # Just return the first result if there is more than one. This
            # should be rare, and they're ordered by relevance.
            return matches.result.docs[0]

    return matches


def make_stats_variable(search_form, paged_results):
    """Create a useful facet variable for use in a template

    This function merges the fields in the form with the facet counts from
    Solr, creating useful variables for the front end.

    We need to handle two cases:
      1. Page loads where we don't have facet values. This can happen when the
         search was invalid (bad date formatting, for example), or when the
         search itself crashed (bad Solr syntax, for example).
      2. A regular page load, where everything worked properly.

    In either case, the count value is associated with the form fields as an
    attribute named "count". If the search didn't work, the value will be None.
    If it did, the value will be an int.
    """
    facet_fields = []
    try:
        solr_facet_values = dict(paged_results.object_list.facet_counts
                                 .facet_fields['status_exact'])
    except (AttributeError, KeyError):
        # AttributeError: Query failed.
        # KeyError: Faceting not enabled on field.
        solr_facet_values = {}

    for field in search_form:
        if not field.html_name.startswith('stat_'):
            continue

        try:
            count = solr_facet_values[field.html_name.replace('stat_', '')]
        except KeyError:
            # Happens when a field is iterated on that doesn't exist in the
            # facets variable
            count = None

        field.count = count
        facet_fields.append(field)
    return facet_fields


def merge_form_with_courts(courts, search_form):
    """Merges the courts dict with the values from the search form.

    Final value is like (note that order is significant):
    courts = {
        'federal': [
            {'name': 'Eighth Circuit',
             'id': 'ca8',
             'checked': True,
             'jurisdiction': 'F',
             'has_oral_argument_scraper': True,
            },
            ...
        ],
        'district': [
            {'name': 'D. Delaware',
             'id': 'deld',
             'checked' False,
             'jurisdiction': 'FD',
             'has_oral_argument_scraper': False,
            },
            ...
        ],
        'state': [
            [{}, {}, {}][][]
        ],
        ...
    }

    State courts are a special exception. For layout purposes, they get
    bundled by supreme court and then by hand. Yes, this means new state courts
    requires manual adjustment here.
    """
    # Are any of the checkboxes checked?
    checked_statuses = [field.value() for field in search_form
                        if field.html_name.startswith('court_')]
    no_facets_selected = not any(checked_statuses)
    all_facets_selected = all(checked_statuses)
    court_count = len([status for status in checked_statuses if status is True])
    court_count_human = court_count
    if all_facets_selected:
        court_count_human = 'All'

    for field in search_form:
        if no_facets_selected:
            for court in courts:
                court.checked = True
        else:
            for court in courts:
                # We're merging two lists, so we have to do a nested loop
                # to find the right value.
                if 'court_%s' % court.pk == field.html_name:
                    court.checked = field.value()
                    break

    # Build the dict with jurisdiction keys and arrange courts into tabs
    court_tabs = {
        'federal': [],
        'district': [],
        'bankruptcy': [],
        'state': [],
        'special': [],
    }
    bap_bundle = []
    b_bundle = []
    state_bundle = []
    state_bundles = []
    for court in courts:
        if court.jurisdiction == Court.FEDERAL_APPELLATE:
            court_tabs['federal'].append(court)
        elif court.jurisdiction == Court.FEDERAL_DISTRICT:
            court_tabs['district'].append(court)
        elif court.jurisdiction in Court.BANKRUPTCY_JURISDICTIONS:
            # Bankruptcy gets bundled into BAPs and regular courts.
            if court.jurisdiction == Court.FEDERAL_BANKRUPTCY_PANEL:
                bap_bundle.append(court)
            else:
                b_bundle.append(court)
        elif court.jurisdiction in Court.STATE_JURISDICTIONS:
            # State courts get bundled by supreme courts
            if court.jurisdiction == Court.STATE_SUPREME:
                # Whenever we hit a state supreme court, we append the
                # previous bundle and start a new one.
                if state_bundle:
                    state_bundles.append(state_bundle)
                state_bundle = [court]
            else:
                state_bundle.append(court)
        elif court.jurisdiction in [Court.FEDERAL_SPECIAL, Court.COMMITTEE,
                                    Court.INTERNATIONAL]:
            court_tabs['special'].append(court)
    state_bundles.append(state_bundle)  # append the final state bundle after the loop ends. Hack?

    # Put the bankruptcy bundles in the courts dict
    court_tabs['bankruptcy'].append(bap_bundle)
    court_tabs['bankruptcy'].append(b_bundle)

    # Divide the state bundles into the correct partitions
    court_tabs['state'].append(state_bundles[:17])
    court_tabs['state'].append(state_bundles[17:34])
    court_tabs['state'].append(state_bundles[34:])

    return court_tabs, court_count_human, court_count


def make_fq(cd, field, key):
    """Does some minimal processing of the query string to get it into a
    proper field query.

    This is necessary because despite our putting AND as the default join
    method, in some cases Solr decides OR is a better approach. So, to work
    around this bug, we do some minimal query parsing ourselves.
    """
    q = cd[key]
    q = q.replace(':', ' ')

    if q.startswith('"') and q.endswith('"'):
        # User used quotes. Just pass it through.
        return '%s:(%s)' % (field, q)

    # Iterate over the query word by word. If the word is a conjunction
    # word, detect that and use the user's request. Else, make sure there's
    # an AND everywhere there should be.
    words = q.split()
    clean_q = [words[0]]
    needs_default_conjunction = True
    for word in words[1:]:
        if word.lower() in ['and', 'or', 'not']:
            clean_q.append(word.upper())
            needs_default_conjunction = False
        else:
            if needs_default_conjunction:
                clean_q.append('AND')
            clean_q.append(word)
            needs_default_conjunction = True
    fq = '%s:(%s)' % (field, ' '.join(clean_q))
    return fq


def make_boolean_fq(cd, field, key):
    return '%s:%s' % (field, str(cd[key]).lower())


def make_fq_proximity_query(cd, field, key):
    """Make an fq proximity query, attempting to normalize and user input.

    This neuters the citation query box, but at the same time ensures that a
    query for 22 US 44 doesn't return an item with parallel citations 22 US 88
    and 44 F.2d 92. I.e., this ensures that queries don't span citations. This
    works because internally Solr uses proximity to create multiValue fields.

    See: http://stackoverflow.com/a/33858649/64911 and
         https://github.com/freelawproject/courtlistener/issues/381
    """
    # Remove all valid Solr tokens, replacing with a space.
    q = re.sub('[\^\?\*:\(\)!\"~\-\[\]]', ' ', cd[key])

    # Remove all valid Solr words
    tokens = []
    for token in q.split():
        if token not in ['AND', 'OR', 'NOT', 'TO']:
            tokens.append(token)
    return '%s:("%s"~5)' % (field, ' '.join(tokens))


def make_date_query(query_field, before, after):
    """Given the cleaned data from a form, return a valid Solr fq string"""
    if any([before, after]):
        if hasattr(after, 'strftime'):
            date_filter = '[%sT00:00:00Z TO ' % after.isoformat()
        else:
            date_filter = '[* TO '
        if hasattr(before, 'strftime'):
            date_filter = '%s%sT23:59:59Z]' % (date_filter, before.isoformat())
        else:
            date_filter = '%s*]' % date_filter
    else:
        # No date filters were requested
        return ""
    return '%s:%s' % (query_field, date_filter)


def make_cite_count_query(cd):
    """Given the cleaned data from a form, return a valid Solr fq string"""
    start = cd.get('cited_gt') or u'*'
    end = cd.get('cited_lt') or u'*'
    if start == '*' and end == '*':
        return ""
    else:
        return 'citeCount:[%s TO %s]' % (start, end)


def get_selected_field_string(cd, prefix):
    """Pulls the selected checkboxes out of the form data, and puts it into
    Solr strings. Uses a prefix to know which items to pull out of the cleaned
    data. Check forms.py to see how the prefixes are set up.

    Final strings are of the form "A" OR "B" OR "C", with quotes in case there
    are spaces in the values.
    """
    selected_fields = ['"%s"' % k.replace(prefix, '')
                       for k, v in cd.items()
                       if (k.startswith(prefix) and v is True)]
    if len(selected_fields) == cd["_%scount" % prefix]:
        # All the boxes are checked. No need for filtering.
        return ''
    else:
        selected_field_string = ' OR '.join(selected_fields)
        return selected_field_string


def make_boost_string(fields):
    qf_array = []
    for k, v in fields.items():
        qf_array.append('%s^%s' % (k, v))
    return ' '.join(qf_array)


def add_boosts(main_params, cd):
    """Add any boosts that make sense for the query."""
    if cd['type'] == 'o' and main_params['sort'].startswith('score'):
        main_params['boost'] = 'pagerank'

    # Apply standard qf parameters
    qf = boosts['qf'][cd['type']].copy()
    main_params['qf'] = make_boost_string(qf)

    if cd['type'] in ['o', 'r', 'oa']:
        # Give a boost on the case_name field if it's obviously a case_name
        # query.
        vs_query = any([' v ' in main_params['q'],
                        ' v. ' in main_params['q'],
                        ' vs. ' in main_params['q']])
        in_re_query = main_params['q'].lower().startswith('in re ')
        matter_of_query = main_params['q'].lower().startswith('matter of ')
        ex_parte_query = main_params['q'].lower().startswith('ex parte ')
        if any([vs_query, in_re_query, matter_of_query, ex_parte_query]):
            qf.update({'caseName': 50})
            main_params['qf'] = make_boost_string(qf)

    # Apply phrase-based boosts
    if cd['type'] in ['o', 'r', 'oa']:
        main_params['pf'] = make_boost_string(boosts['pf'][cd['type']])
        main_params['ps'] = 5


def add_faceting(main_params, cd, facet):
    """Add any faceting filters to the query."""
    if not facet:
        # Faceting is off. Do nothing.
        return

    facet_params = {}
    if cd['type'] == 'o':
        facet_params = {
            'facet': 'true',
            'facet.mincount': 0,
            'facet.field': '{!ex=dt}status_exact',
        }
    main_params.update(facet_params)


def add_highlighting(main_params, cd, highlight):
    """Add any parameters relating to highlighting."""

    if not highlight:
        # highlighting is off, therefore we get the default fl parameter,
        # which gives us all fields. We could set it manually, but there's
        # no need.
        return

    # Common highlighting params up here.
    main_params.update({
        'hl': 'true',
        'f.text.hl.snippets': '5',
        'f.text.hl.maxAlternateFieldLength': '500',
        'f.text.hl.alternateField': 'text',
    })

    if highlight == 'text':
        main_params['hl.fl'] = 'text'
        return

    assert highlight == 'all', "Got unexpected highlighting value."
    # Requested fields for the main query. We only need the fields
    # here that are not requested as part of highlighting. Facet
    # params are not set here because they do not retrieve results,
    # only counts (they are set to 0 rows).
    if cd['type'] == 'o':
        fl = ['absolute_url', 'citeCount', 'court_id', 'dateFiled',
              'download_url', 'id',  'local_path', 'sibling_ids', 'source',
              'status']
        hlfl = ['caseName', 'citation', 'court_citation_string', 'docketNumber',
                'judge', 'lexisCite', 'neutralCite', 'suitNature', 'text']
    elif cd['type'] == 'r':
        fl = ['absolute_url', 'assigned_to_id', 'attachment_number', 'attorney',
              'court_id', 'dateArgued', 'dateFiled', 'dateTerminated',
              'docket_absolute_url', 'docket_id', 'document_number', 'id',
              'is_available', 'page_count', 'party', 'referred_to_id']
        hlfl = ['assignedTo', 'caseName', 'cause', 'court_citation_string',
                'docketNumber', 'juryDemand', 'referredTo', 'short_description',
                'suitNature', 'text']
    elif cd['type'] == 'oa':
        fl = ['id', 'absolute_url', 'court_id', 'local_path', 'source',
              'download_url', 'docket_id', 'dateArgued', 'duration']
        hlfl = ['text', 'caseName', 'judge', 'docketNumber',
                'court_citation_string']
    elif cd['type'] == 'p':
        fl = ['id', 'absolute_url', 'dob', 'date_granularity_dob', 'dod',
              'date_granularity_dod', 'political_affiliation',
              'aba_rating', 'school', 'appointer', 'supervisor', 'predecessor',
              'selection_method', 'court']
        hlfl = ['name', 'dob_city', 'dob_state', 'name_reverse']

    main_params.update({
        'fl': ','.join(fl),
        'hl.fl': ','.join(hlfl),
    })
    for field in hlfl:
        if field == 'text':
            continue
        main_params['f.%s.hl.fragListBuilder' % field] = 'single'
        main_params['f.%s.hl.alternateField' % field] = field


def add_filter_queries(main_params, cd):
    """Add the fq params"""
    # Changes here are usually mirrored in place_facet_queries, below.
    main_fq = []

    if cd['type'] == 'o':
        if cd['case_name']:
            main_fq.append(make_fq(cd, 'caseName', 'case_name'))
        if cd['judge']:
            main_fq.append(make_fq(cd, 'judge', 'judge'))
        if cd['docket_number']:
            main_fq.append(make_fq(cd, 'docketNumber', 'docket_number'))
        if cd['citation']:
            main_fq.append(make_fq_proximity_query(cd, 'citation', 'citation'))
        if cd['neutral_cite']:
            main_fq.append(make_fq(cd, 'neutralCite', 'neutral_cite'))
        main_fq.append(make_date_query('dateFiled', cd['filed_before'],
                                       cd['filed_after']))

        # Citation count
        cite_count_query = make_cite_count_query(cd)
        main_fq.append(cite_count_query)

    elif cd['type'] == 'r':
        if cd['case_name']:
            main_fq.append(make_fq(cd, 'caseName', 'case_name'))
        if cd['description']:
            main_fq.append(make_fq(cd, 'description', 'description'))
        if cd['docket_number']:
            main_fq.append(make_fq(cd, 'docketNumber', 'docket_number'))
        if cd['nature_of_suit']:
            main_fq.append(make_fq(cd, 'suitNature', 'nature_of_suit'))
        if cd['cause']:
            main_fq.append(make_fq(cd, 'cause', 'cause'))
        if cd['document_number']:
            main_fq.append(make_fq(cd, 'document_number', 'document_number'))
        if cd['attachment_number']:
            main_fq.append(make_fq(cd, 'attachment_number', 'attachment_number'))
        if cd['assigned_to']:
            main_fq.append(make_fq(cd, 'assignedTo', 'assigned_to'))
        if cd['referred_to']:
            main_fq.append(make_fq(cd, 'referredTo', 'referred_to'))
        if cd['available_only']:
            main_fq.append(make_boolean_fq(cd, 'is_available', 'available_only'))
        if cd['party_name']:
            main_fq.append(make_fq(cd, 'party', 'party_name'))
        if cd['atty_name']:
            main_fq.append(make_fq(cd, 'attorney', 'atty_name'))

        main_fq.append(make_date_query('dateFiled', cd['filed_before'],
                                       cd['filed_after']))

    elif cd['type'] == 'oa':
        if cd['case_name']:
            main_fq.append(make_fq(cd, 'caseName', 'case_name'))
        if cd['judge']:
            main_fq.append(make_fq(cd, 'judge', 'judge'))
        if cd['docket_number']:
            main_fq.append(make_fq(cd, 'docketNumber', 'docket_number'))
        main_fq.append(make_date_query('dateArgued', cd['argued_before'],
                                       cd['argued_after']))

    elif cd['type'] == 'p':
        if cd['name']:
            main_fq.append(make_fq(cd, 'name', "name"))
        if cd['dob_city']:
            main_fq.append(make_fq(cd, 'dob_city', 'dob_city'))
        if cd['dob_state']:
            main_fq.append(make_fq(cd, 'dob_state_id', 'dob_state'))
        if cd['school']:
            main_fq.append(make_fq(cd, 'school', 'school'))
        if cd['appointer']:
            main_fq.append(make_fq(cd, 'appointer', 'appointer'))
        if cd['selection_method']:
            main_fq.append(make_fq(cd, 'selection_method_id', 'selection_method'))
        if cd['political_affiliation']:
            main_fq.append(make_fq(cd, 'political_affiliation_id', 'political_affiliation'))
        main_fq.append(make_date_query('dob', cd['born_before'],
                                       cd['born_after']))

    # Facet filters
    if cd['type'] == 'o':
        selected_stats_string = get_selected_field_string(cd, 'stat_')
        if len(selected_stats_string) > 0:
            main_fq.append('{!tag=dt}status_exact:(%s)' % selected_stats_string)

    selected_courts_string = get_selected_field_string(cd, 'court_')
    if len(selected_courts_string) > 0:
        main_fq.append('court_exact:(%s)' % selected_courts_string)

    # If a param has been added to the fq variables, then we add them to the
    # main_params var. Otherwise, we don't, as doing so throws an error.
    if len(main_fq) > 0:
        if 'fq' in main_params:
            main_params['fq'].append(main_fq)
        else:
            main_params['fq'] = main_fq


def add_grouping(main_params, cd, group):
    """Add any grouping parameters."""
    if cd['type'] == 'o':
        # Group clusters. Because this uses faceting, we use the collapse query
        # parser here instead of the usual result grouping. Faceting with
        # grouping has terrible performance.
        group_fq = "{!collapse field=cluster_id sort='type asc'}"
        if 'fq' in main_params:
            main_params['fq'].append(group_fq)
        else:
            main_params['fq'] = group_fq

    elif cd['type'] == 'r' and group is True:
        docket_query = re.match('docket_id:\d+', cd['q'])
        group_params = {
            'group': 'true',
            'group.ngroups': 'true',
            'group.limit': 5 if not docket_query else 500,
            'group.field': 'docket_id',
            'group.sort': 'score desc',
        }
        main_params.update(group_params)


def regroup_snippets(results):
    """Regroup the snippets in a grouped result.

    Grouped results will have snippets for each of the group members. Some of
    the snippets will be the same because they're the same across all items in
    the group. For example, every opinion in the opinion index contains the
    name of the attorneys. So, if we have a match on the attorney name, that'll
    generate a snippet for both the lead opinion and a dissent.

    In this function, we identify these kinds of duplicates and pull them out.
    We also flatten the results so that snippets are easier to get.

    This also supports results that have been paginated and ones that have not.
    """
    if results is None:
        return

    if hasattr(results, 'paginator'):
        group_field = results.object_list.group_field
    else:
        group_field = results.group_field
    if group_field is not None:
        if hasattr(results, 'paginator'):
            groups = getattr(results.object_list.groups, group_field)['groups']
        else:
            groups = results

        for group in groups:
            snippets = []
            for doc in group['doclist']['docs']:
                for snippet in doc['solr_highlights']['text']:
                    if snippet not in snippets:
                        snippets.append(snippet)
            group['snippets'] = snippets


def print_params(params):
    if settings.DEBUG:
        print("Params sent to search are:\n%s" % ' &\n'.join(
            ['  %s = %s' % (k, v) for k, v in params.items()]
        ))
        # print results_si.execute()


def build_main_query(cd, highlight='all', order_by='', facet=True, group=True):
    main_params = {
        'q': cd['q'] or '*',
        'sort': cd.get('order_by', order_by),
        'caller': 'build_main_query',
    }
    add_faceting(main_params, cd, facet)
    add_boosts(main_params, cd)
    add_highlighting(main_params, cd, highlight)
    add_filter_queries(main_params, cd)
    add_grouping(main_params, cd, group)
    handle_related_query(main_params)

    print_params(main_params)
    return main_params


def build_coverage_query(court, q):
    params = {
        'facet': 'true',
        'facet.range': 'dateFiled',
        'facet.range.start': '1600-01-01T00:00:00Z',  # Assume very early date.
        'facet.range.end': 'NOW/DAY',
        'facet.range.gap': '+1YEAR',
        'rows': 0,
        'q': q or '*',  # Without this, results will be omitted.
        'caller': 'build_coverage_query',
    }
    if court.lower() != 'all':
        params['fq'] = ['court_exact:%s' % court]
    return params


def build_court_count_query():
    """Build a query that returns the count of cases for all courts"""
    params = {
        'q': '*',
        'facet': 'true',
        'facet.field': 'court_exact',
        'facet.limit': -1,
        'rows': 0,
        'caller': 'build_court_count_query',
    }
    return params

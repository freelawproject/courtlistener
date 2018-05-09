import re

from cl.recommendations.models import OpinionRecommendation


def handle_related_query(main_params):
    """Handles the keyword prefix query "related:". The prefix limits the search
    space to documents related to a given seed document. The seed document is
    defined with a document identifier directly after the keyword.

    Format: related:<content_type><content_id>
    Example: related:opinion1

    The keyword prefix query can be combined with other queries:

    Format: related:<content_type><content_id> <other_query>
    Example: related:opinion1 foo bar

    In order to limit the search space, related documents with the corresponding
    ids and scores are first retrieved from database. Based on the relatedness
    information we extend the query filter (qf) and boost specific ids with their
    scores (in q) in the original Solr query.

    recommendations:q
    -> q=original_query+(id:rec1^10 + rec_score1)+(id:rec2^10+ rec_score2 ...)
    -> fq=(id:rec1 OR id:rec2)...
    -> disable other boosts

    :param main_params: Pre-generated params for the Solr query
    """
    related_prefix_match = re.search(r'^related:(opinion|docket|person|audio)([0-9]+)(.*)', main_params['q'])
    if related_prefix_match:
        content_type = related_prefix_match.group(1)
        content_id = int(related_prefix_match.group(2))
        original_query = related_prefix_match.group(3).strip()

        print('Related for {} #{}'.format(content_type, content_id))

        # Retrieve recommendations
        recs = OpinionRecommendation.objects\
            .filter(seed_id=content_id)\
            .order_by('-score')\
            .values('recommendation_id', 'score')

        if recs:
            # Remove prefix from query
            if original_query == '':
                main_params['q'] = '*'  # Ignore combined queries
            else:
                main_params['q'] = original_query

            # Build filters and boosts
            filter_ids = []
            boost_ids = []
            for i, rec in enumerate(recs):
                print(rec)
                filter_ids.append('id:{}'.format(rec['recommendation_id']))
                boost_ids.append('(id:{}^{})'.format(rec['recommendation_id'], (len(recs) - i) * 100))  # 1000 + float(rec['score'])

            main_params['fq'].append(' OR '.join(filter_ids))
            main_params['q'] += ' (' + (' '.join(boost_ids)) + ')'
            # del main_params['qf']  # = None  # query fields

            if 'boost' in main_params:  # Unset previous boost (if order_by=relevance)
                del main_params['boost']

            # del main_params['pf']

            # main_params['q'] = ' (' + (' '.join(rec_boosts)) + ')'  #+ main_params['q']
            # main_params['q'] += ' (id:89^100)'
        else:
            # no related info found
            pass

        # main_fq.append('id:20 OR id:17')
        # main_fq.append('id:50')

        print(main_params['fq'])

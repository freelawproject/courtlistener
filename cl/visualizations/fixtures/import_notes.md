During testing, it's possible to import the generated JSON in a Python command. This process will undoubtedly change, but until it does, the process is:

First, import your json:

    import json
    j = json.loads("""{your json here}""")
    
Then, iterate over it, creating dockets, clusters, and opinions:
 
    from cl.search.models import OpinionCluster, OpinionsCited, Opinion, Docket, Court
    from django.utils.timezone import now
    import dateutil
    court = Court.objects.get(pk='scotus')
    for d in j['opinion_clusters']:
        print "Making stuff for: %s" % d['id']
        docket = Docket(pk=d['id'], date_created=now(), date_modified=now(), 
                        court_id='scotus', case_name_short=d['case_name_short'], 
                        case_name=d['case_name'])
        docket.save()
        cluster = OpinionCluster(
            pk=d['id'], docket=docket, date_created=now(), date_modified=now(), 
            date_filed=dateutil.parser.parse(d['date_filed']), 
            case_name_short=d['case_name_short'], case_name=d['case_name'],
            scdb_decision_direction=d['decision_direction'], 
            scdb_votes_majority=d['votes_majority'], 
            scdb_votes_minority=d['votes_minority'], source='M', 
            precedential_status='Published', citation_count=d['citation_count']
        )
        cluster.save(index=False)
        opinion = Opinion(pk=d['id'], cluster=cluster, date_created=now(), 
                          date_modified=now(), type='010combined', sha1='asdf')
        opinion.save(index=False)


Then add the citation relationships:

    for d in j['opinion_clusters']:
        for cited_id in d['sub_opinions'][0]['opinions_cited']:
            op = OpinionsCited(citing_opinion_id=d['id'], cited_opinion_id=cited_id)
            try:
                op.save()
                print "Saved successfully!"
            except IntegrityError:
                print "No such document, %s" % cited_id

If all goes well, you should be all set.

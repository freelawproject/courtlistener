To do:
 - check out the outliars in the DB by date
 - recreate the stat_maker.py script (see bug)
 - Check the dates/courts in Brian's list of citation-less docs, and see if we
   missed any docs.
 - Do F3
    - Fix the "change this doc" docs in F3
    - export/import the latest court db, and update the install script.
    - add fiscr to the various places on the site where it's needed...


SOLR
 - search for 2d doesn't highlight in the case title (issue 199)


SOLR DEPLOYMENT:
    - Update all user alerts
        - possibly useful: select au.first_name, au.last_name, au.email, au.username, a.alertName, a.alertText, a.alertFrequency from Alert a left outer join UserProfile_alert upa on upa.alert_id = a.alertUUID left outer join UserProfile up on upa.userprofile_id = up.userProfileUUID left outer join auth_user au on au.id = up.user_id order by au.email;

 - Ensure that the rabbit-mq, celery and solr will start up at reboot
 - check speed, ram, CPUs
 - fix issue with encodings...somehow.
     
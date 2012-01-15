To do:
 - check out the outliars in the DB by date
 - recreate the stat_maker.py script (see bug)
 - Check the dates/courts in Brian's list of citation-less docs, and see if we
   missed any docs.
 - Do F3
    - Fix the "change this doc" docs in F3
    - export/import the latest court db, and update the install script.
    - add fiscr to the various places on the site where it's needed...


Features:
 + Boosting of status, casename, and casenumber
 + Result counts
 + Faceted search
    + facet counts with parallel selection
        + court
        + status
    + field filtering
        + filed date
        + casename
        + west citation
        + docket number
 + Result ordering
 + New/previous search radio buttons
 + Realtime indexing via Celery
 + DB to index script
 + Homepage shows all results
 + Snippets with multiple fragments
 + Highlighting on all returned fields
 - Multicore should be investigated/implemented
 - RAM tuning should be investigated/implemented
 - Result speed?



QA:
 - Check for proper alert deletion and editing functionality, since code rewritten. Tests:
    - can I delete/edit YOUR alert?
    - what happens if I try to hack the URL bar with non-ints?
        - if OK, try it without the int check in the delete_alert and edit_alert functions
 + Check that the tools page works (code moved but untested)
 - Test that length of the search isn't limited (length of what? The query or the number of results?)
 - Test that Univ. and other v's are fixed so they are only italicized when necessary
 - Ensure that the rabbit-mq, celery and solr will start up at reboot
 - Test whether q='' works
 + Test proper pluralization of results
 - Test with and without JS
 - Test where items are placed when they lack a date and date sorting is used
 - Is there a limit to the number of results? Do we handle it? 
 - Does Piwik still work?
 - Do placeholders work in IE6-9?
 - Test that the various display logic still works for displaying the result meta data (exercise all the if/else statements)
 - make sure that the next functionsn work from the register and sign-in pages, and the save favorite popup
 - test that dumps still work
 - test acct deletion
 - verify search parity:
    - prefix/infix searching
    - phrases
    - facets
        - status:blah works?
    - etc.
 - remove all print lines
 - run pylint for a few hours
     - check for TODO statements
 - test the various IEs
 
    
 
SOLR
 - search for 2d doesn't highlight in the case title (issue 199)


SOLR DEPLOYMENT:
 - install Solr (see script)
 - install daemon
 - cron:
    - remove Sphinx @restart cron job <-- this should match the installer cron jobs.
    - add any Solr indexing cron jobs --> NONE!
    - change the alerts to use mly, wkly and dly
 - Run:
    sudo update-rc.d solr defaults
    sudo update-rc.d celeryd defaults
    # Fix the init.d link for the scraper:
    sudo rm /etc/init.d/scraper
    sudo ln -s /var/www/court-listener/init-scripts/scraper /etc/init.d/scraper
    sudo update-rc.d scraper defaults
    
 - hg pull -u
 - upgrade Django:
    - svn switch -r 17237 http://code.djangoproject.com/svn/django/branches/releases/1.3.X
    - update 20-private to have this: 'ENGINE': 'django.db.backends.mysql',
    - restart apache2
 - reindex 
    - How big will our index be? Space on disk, or do we need to remove Sphinx first?
        - Should be OK. There are 736 docs on my local system, which require 22MB.
        - There are 815 times more docs on the live system, which means they will take 17.5GB
        - SSD Disk has ~50GB free.  
    - python manage.py update_index --update --everything
 - Synchronize the database for the refactoring changes:
        update django_content_type set app_label = 'alerts' where name='alert';
        update django_content_type set app_label = 'favorites' where name='favorite';
        update django_content_type set app_label = 'scrapers' where name='url to hash';
        update django_content_type set app_label = 'search' where name='court';
        update django_content_type set app_label = 'search' where name='citation';
        update django_content_type set app_label = 'search' where name='document';
        
        python manage.py reset south
        
        mysql> insert into south_migrationhistory set app_name='alerts', migration='0001_initial', applied='2011-12-01'; -- fakes the convert_to_south command
        mysql> insert into south_migrationhistory set app_name='userHandling', migration='0001_initial', applied='2011-12-01'; -- fakes the convert_to_south command
        mysql> insert into south_migrationhistory set app_name='favorites', migration='0001_initial', applied='2011-12-01'; -- fakes the convert_to_south command
        mysql> insert into south_migrationhistory set app_name='scrapers', migration='0001_initial', applied='2011-12-01'; -- fakes the convert_to_south command
        mysql> insert into south_migrationhistory set app_name='search', migration='0001_initial', applied='2011-12-01'; # fakes the convert_to_south command
        python manage.py migrate search --auto #runs the migration needed on this model
        python manage.py migrate alerts
        
        # Don't think this is necessary. Not sure why it's here.
        python manage.py syncdb
    - Update all user alerts
        - possibly useful: select au.first_name, au.last_name, au.email, au.username, a.alertName, a.alertText, a.alertFrequency from Alert a left outer join UserProfile_alert upa on upa.alert_id = a.alertUUID left outer join UserProfile up on upa.userprofile_id = up.userProfileUUID left outer join auth_user au on au.id = up.user_id order by au.email;
        
 
 - uninstall Sphinx!
    - remove Sphinx logs
    - remove Sphinx indexes
    - remove Sphinx configs
    - remove database table: drop table sph_counter;
    
  note to blog:
    - big overhaul, lots of new features
        - relevance and date-based sorting
        - highlighting
        - faceted search
        - snippets
        - unlimited result pagination?
        - real-time search indexes
    - lost a couple things:
        - some search connectors
    - all alerts updated by hand. Will get an email from us if we have any issues
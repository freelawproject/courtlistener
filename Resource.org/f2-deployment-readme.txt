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
 - Boosting of status, casename, and casenumber
 - Result counts
 - Faceted search
    - facet counts with parallel selection
        - court
        - status
    - field filtering
        - filed date
        - casename
        - west citation
        - docket number
 - Result ordering
 - New/previous search radio buttons
 - Realtime indexing via Celery
 - DB to index script
 - Homepage shows all results
 - Snippets with multiple fragments
 - Highlighting on all returned fields
 - Multicore should be investigated/implemented
 - RAM tuning should be investigated/implemented
 

    
QA:
 - Check for proper alert deletion and editing functionality, since code rewritten. Tests:
    - can I delete/edit YOUR alert?
    - what happens if I try to hack the URL bar with non-ints?
        - if OK, try it without the int check in the delete_alert and edit_alert functions
 - Check that the tools page works (code moved but untested)
 - Test that length of the search isn't limited (length of what? The query or the number of results?)
 - Test that Univ. and other v's are fixed so they are only italicized when necessary
 - Ensure that the rabbit-mq, celery and solr will start up at reboot
 - Test whether q='' works
 - Test proper pluralization of results
 - Test with and without JS
 - Test where items are placed when they lack a date and date sorting is used
 - Is there a limit to the number of results? Do we handle it? 
 
    
 
SOLR + Haystack!
 - Finish the configuration of solr in the installer
 - create database crawler to import entire thing into Solr

 - update all places that search can be performed in the project
    - RSS feeds
    - Alerts
        - There were X new results for your Alert. Here are the first 15.
        - TOC at top of alerts with HTML anchors.
    - Front end
 - update flat advanced search page
 - add xxx-xx-xxxx etc to the stopwords list (#190)
 - change case title from Courtlistener.com / Browse / Foo --> / Cases / Foo
 - consider/resolve old URL support. What does /opinions/all/ do? What about /opinions/ca2/, etc? 
 - add information about date/time formats. Useful to tell people that they can use timestamps or just dates. It 
   might be worth investigating django forms help_text for this.  


SOLR DEPLOYMENT:
 - install Solr (see script)
 - install daemon
 - remove Sphinx @restart cron job <-- this should match the installer cron jobs.
 - add any Solr indexing cron jobs
 - Run:
    sudo update-rc.d solr defaults
    sudo update-rc.d celeryd defaults
    # Fix the init.d link for the scraper:
    sudo rm /etc/init.d/scraper
    sudo ln -s /var/www/court-listener/init-scripts/scraper /etc/init.d/scraper
    sudo update-rc.d scraper defaults
    
 - hg pull -u
    - adjust the apache config to point to the new robots.txt location (tinyurl/robots.txt)
 - reindex 
    - How big will our index be? Space on disk, or do we need to remove Sphinx first?
        - Should be OK. There are 736 docs on my local system, which require 22MB.
        - There are 815 times more docs on the live system, which means they will take 17.5GB
        - SSD Disk has ~50GB free.  
    - python manage.py rebuild_index -k 4 -b 1000 -v 2
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
        
        # Don't think this is necessary. Not sure why it's here.
        python manage.py syncdb
 
 - uninstall Sphinx!
    - remove Sphinx logs
    - remove Sphinx indexes
    - remove Sphinx configs
    - remove database table: drop table sph_counter;
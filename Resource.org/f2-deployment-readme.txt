To do:
 - check out the outliars in the DB by date
 - recreate the stat_maker.py script (see bug)
 - Check the dates/courts in Brian's list of citation-less docs, and see if we
   missed any docs.
 - Do F3
    - Fix the "change this doc" docs in F3
    - export/import the latest court db, and update the install script.
    - add fiscr to the various places on the site where it's needed...


    
QA:
 - Check for proper alert deletion and editing functionality, since code rewritten. Tests:
    - can I delete/edit YOUR alert?
    - what happens if I try to hack the URL bar with non-ints?
        - if OK, try it without the int check in the delete_alert and edit_alert functions
 - Check that the tools page works (code moved but untested)
 - Test that length of the search isn't limited
 - Test that Univ. and other v's are fixed so they are only italicized when necessary
 - Ensure that the rabbit-mq, celery and solr will start up at reboot
 
    
 
SOLR + Haystack!
 - Finish the configuration of solr in the installer
 - create celery task for indexing cases as they come in
 - create database crawler to import entire thing into Solr
 - build faceted search
    - remove homepage! <-- Done
    - remove browse code! <-- Done
    - get Haystack talking to Solr to perform a basic search
        - Research: what does multicore mean - do we need it?
    - get results sorted out so they look good
    - build up the facets/sort fields etc.
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
        python manage.py convert_to_south alerts
        python manage.py convert_to_south userHandling
        python manage.py convert_to_south favorites
        python manage.py convert_to_south search
        python manage.py convert_to_south scrapers
      
        python manage.py syncdb
 
 - uninstall Sphinx!
    - remove Sphinx logs
    - remove Sphinx indexes
    - remove Sphinx configs
    - remove database table: drop table sph_counter;
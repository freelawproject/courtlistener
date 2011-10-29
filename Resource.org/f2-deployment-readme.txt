To do:
 - check out the outliars in the DB by date
 - recreate the stat_maker.py script (see bug)
 - Check the dates/courts in Brian's list of citation-less docs, and see if we
   missed any docs.
 - Do F3
    - Fix the "change this doc" docs in F3
    - export/import the latest court db, and update the install script.
    - add fiscr to the various places on the site where it's needed...
 
Install
 - The sphinx config is out of date


CLEANUP
 - alertSystem
    - Move views to favorites app
    - Move models and admin to search app
    - Move redirection code to its own app, including robots.txt
    - Move template/display_cases.html to display_case.html
    - Rename as simply alerts
    - remove migrations, and reset the south config (live and dev)
 - search
    - Move alert views to the alerts app
    - Remove the tools view - make it a flat page...if possible. 
 - URLs
    - move the huge URLs file to various smaller ones
 
    
 
SOLR + Haystack!
 - update restart command in log file
 - remove all sphinx references
 - install haystack and Solr - update the installer as needed
    - update the installer cronjobs notes
 - create celery task for indexing cases as they come in
 - create database crawler to import entire thing into Solr
 - build faceted search
    - remove homepage!
    - remove browse code!
    - get Haystack talking to Solr to perform a basic search
    - get results sorted out so they look good
    - build up the facets/sort fields etc.
 - update all places that search can be performed in the project
    - RSS feeds
    - Alerts
    - Front end
 - update flat advanced search page
 - add xxx-xx-xxxx etc to the stopwords list (#190)


SOLR DEPLOYMENT:
 - install Solr
 - update Sphinx/Solr cron jobs <-- this should match the installer cron jobs.
 - reindex <-- How big will our index be? Space on disk, or do we need to remove Sphinx first? 
 - hg pull -u
 - uninstall Sphinx!
    - remove Sphinx logs
    - remove Sphinx indexes
    - remove Sphinx configs
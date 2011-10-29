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
 
 
SOLR + Haystack!
 - set up logging
 - remove all sphinx references
 - install haystack and Solr - update the installer as needed
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
 - update Sphinx/Solr cron jobs
 - reindex <-- How big will our index be? Space on disk, or do we need to remove Sphinx first? 
 - hg pull -u
 - uninstall Sphinx!
    - remove Sphinx logs
    - remove Sphinx indexes
    - remove Sphinx configs
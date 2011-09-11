To do:
 - check out the outliars in the DB by date
 - recreate the stat_maker.py script (see bug)
 - create queue for parser (or similar, see bug)
 - Check the dates/courts in Brian's list of citation-less docs, and see if we
   missed any docs.
 - Do F3
    - Fix the "change this doc" docs in F3
    - export/import the latest court db, and update the install script.
    - add fiscr to the various places on the site where it's needed...
 - Import resource.org/robots.txt (see bug 187)
 - Why don't I get logs from the scraper daemon emailed?
 
 Robots:
  - set up celery and create tasks for deleting sitemaps when docs are saved/deleted
  - On deploy:
    - migrate models
    - delete all sitemaps
    - update apache to remove robots.txt
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
 
Install
 - The sphinx config is out of date
 

# All dependencies should be set up before this stage
hg pull -u
ran
python manage.py syncdb

# Update cron jobs
 - remove the p flag.
 - change them to scrape_and_extract.py
 
# Restart the scrapers

  
TODO:
 - set the CELERY_AMQP_TASK_RESULT_EXPIRES setting, or else results pile up forever.
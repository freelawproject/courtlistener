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
 
Celery install:
# Set up the celery user
sudo aptitude install rabbitmq-server
sudo rabbitmqctl add_vhost "/celery"
sudo rabbitmqctl add_user celery 'password goes here'
sudo rabbitmqctl set_permissions -p "/celery" "celery" ".*" ".*" ".*"

# Add these credentials to private-20.conf manually.
cl
vi alert/settings/20-private.conf

# Add these lines:
# Celery settings
BROKER_USER = "celery"
BROKER_PASSWORD = "SOME PASSWORD HERE - A GOOD ONE - IT'S NEVER NEEDED"


#install django-celery and celery
sudo pip install django-celery 

# All dependencies should be set up before this stage
hg pull -u
ran
python manage.py syncdb
  
TODO:
 - remove parseCourt, getDocContent
 - remove the word parse. We're extracting, not parsing.
 - update cron jobs to remove the -p flag of the scraper, and restart the scraper.
 - set the CELERY_AMQP_TASK_RESULT_EXPIRES setting, or else results pile up forever.
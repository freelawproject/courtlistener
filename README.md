# CourtListener

Started [in 2009][yours-truly], CourtListener.com is the main initiative of [Free Law Project][flp]. The goal of CourtListener.com is to provide high quality data and services.

## What's Here

This repository is organized in the following way:

 - ansible: ansible playbooks and inventories for setting up and updating your machine.
 - apache: configurations for the Apache webserver.
 - cl: the Django code for this project. 99% of everything is in this directory.
 - docker: Where to find compose files and docker files for various components.
 - cleaning_scripts: cleanup scripts that are used from time to time to fix data issues or errors.
 - OCR: code and files related to our Tesseract OCR configuration.
 - scripts: logrotate, systemd, etc, and init scripts for our various configurations and daemons.


## Getting Involved

If you want to get involved send us an email with your contact info or take a look through the [issues list][issues]. There are innumerable things we need help with, but we especially are looking for help with:

 - legal research in order to fix data errors or other problems (check out the [data-quality label][dq] for some starting points)
 - fixing bugs and building features (most things are written in Python)
 - machine learning or natural language problems. 
 - test writing -- we always need more and better tests

In general, we're looking for all kinds of help. Get in touch if you think you have skills we could use or if you have skills you want to learn by improving CourtListener.


## Contributing code

See the [developer guide][developing].


## Upgrading On the Regular

Each day, when you start working on CourtListener, you should make sure that you have the latest code and dependencies. There are a couple different ways to do this. 
 
The first thing you should do is:

    ansible-playbook ansible/upgrade.yml -i ansible/hosts --ask-become-pass
    
This says to run the tasks in the playbook called `upgrade.yml` on the hosts described in `ansible/hosts` (which is localhost). Get the sudo password, since it may be needed to start/stop services. Pretty simple. 

If you're using Vagrant, you also need to be sure to run any new playbooks that were pulled from git in the command above. These will appear in the `ansible` directory for the version of Free Law Machine that you have installed, and represent all the changes that have been made to it since it was created. So, for example, the first time you start up your Vagrant machine, you should run all of the playbooks in the 1.6.0 directory (assuming that's the version you're running):

    ansible-playbook ansible/1.6.0/0001_update_solr.yml -i ansible/hosts --ask-become-pass
    ansible-playbook ansible/1.6.0/0002_create_recap_core.yml -i ansible/hosts --ask-become-pass
    # etc.

You may want to override the default variables (in defaults.yml) if you have CourtListener installed in a "special" location. To do that you can add something like:

    --extra-vars "install_root=/home/mlissner/Programming/intellij/courtlistener virtualenv_root=/home/mlissner/.virtualenvs/courtlistener"

Just to pick some random examples. 

Any time you see a new playbook come in when you pull code, you should run it in the same way.

If you installed from the Wiki, you should watch for upgrades coming into these folders as well, and should apply them as you see them arrive.


## Upgrading Production

We usually use Ansible for this, but at the moment it's a bit of a mess due to our ongoing dockerization.

The process now is:

 - Check MIGRATIONS.md for potentially critical optimizations to database migrations.
 - Celery:
    - Simple updates to the docker image can be done with (though you usually want to stop it, then get the latest code, then start it as described next):
        - sudo docker pull freelawproject/task-server
        - sudo docker service update task-server_celery_prefork_bulk --image freelawproject/task-server:latest
        - sudo docker service update task-server_celery_prefork --image freelawproject/task-server:latest
        - sudo docker service update task-server_celery_gevent --image freelawproject/task-server:latest
    - Pull latest docker image
        - sudo docker pull freelawproject/task-server
    - Stop celery:
        - sudo docker service scale task-server_celery_prefork=0
        - sudo docker service scale task-server_celery_prefork_bulk=0
        - sudo docker service scale task-server_celery_gevent=0
    - Pull latest code (git):
        - cd /opt/tasks && sudo git pull
 - Solr:
    - Pull latest docker image
    - Pull latest code (git)
    - Restart solr:
        - sudo docker restart solr
 - Web:
    - Run ansible scripts (they still work)
 - Database:
    - default is migrated by ansible
    - migrate replicated database on old CL via SQL 
    psql -h localhost -U django --dbname courtlistener -p 5432 <  /var/www/courtlistener/cl/lasc/migrations/0002_auto_20191004_1431.sql 
    - migrate replicated database on AWS via SQL
    psql -h cl-replica.c3q1wkj3stig.us-west-2.rds.amazonaws.com -U django --dbname courtlistener -p 5432 <  /var/www/courtlistener/cl/lasc/migrations/0002_auto_20191004_1431.sql
 - Celery:
    - Start:
        - sudo docker service scale task-server_celery_prefork=5
        - sudo docker service scale task-server_celery_prefork_bulk=5

    - Monitor: 
        - sudo docker service logs -f --since 1 task-server_celery_prefork
    

These things should happen by way of the above, I think:
 - git pull on all hosts
 - update python dependencies on all hosts
 - update seals if needed
 - collectstatic on any web hosts

### Update


## Copyright

All materials in this repository are copyright Free Law Project under the Affero GPL. See LICENSE.txt for details.


## Contact

To contract Free Law Project, see here:

https://free.law/contact/



[issues]: https://github.com/freelawproject/courtlistener/issues
[hw]: https://github.com/freelawproject/courtlistener/labels/help%20wanted
[dq]: https://github.com/freelawproject/courtlistener/labels/data-quality
[flp]: https://free.law/
[developing]: https://github.com/freelawproject/courtlistener/blob/master/DEVELOPING.md
[yours-truly]: https://github.com/freelawproject/courtlistener/commit/90db0eb433990a7fd5e8cbe5b0fffef5fbf8e4f6

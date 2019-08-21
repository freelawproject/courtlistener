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

This has gotten easy:

    ansible-playbook ansible/upgrade.yml --ask-become-pass

And also run any special ones in any version of Vagrant, just like for Wiki installations.


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

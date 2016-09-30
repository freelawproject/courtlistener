# CourtListener

CourtListener.com is the main initiative of [Free Law Project][flp].

This repository is organized in the following way:

 - ansible: ansible playbooks and inventories for setting up and updating your machine.
 - apache: configurations for the Apache webserver.
 - cl: the Django code for this project. 99% of everything is in this directory.
 - cleaning_scripts: cleanup scripts that are used from time to time to fix data issues or errors.
 - OCR: code and files related to our Tesseract OCR configuration.
 - scripts: logrotate, systemd, etc, and init scripts for our various configurations and daemons.
 - Solr: Anything related to the solr configuration.


## Getting Started

You have two options for installing the CourtListener project. The easiest and recommended way is to use Vagrant:
  
 - https://free.law/2016/03/01/its-easier-than-ever-to-contribute-to-courtlistener-and-free-law-project/

Vagrant provides a VM containing all of the CourtListener dependencies that you can run in headless mode. In this configuration, you can either connect to your VM as if it's a remote computer via SSH, or you can use shared drives (sort of like network folders) to access things inside the VM. You can read more about it at the link above. 

The other, harder way to get set up is to follow the instructions on our wiki:

 - https://github.com/freelawproject/courtlistener/wiki/Installing-CourtListener-on-Ubuntu-Linux

We endeavor to keep these up to date, since for now they are the ground truth in terms of how to set up a new server.


## Getting Involved

If you want to get involved send us an email with your contact info or take a look through the [issues list][issues]. There are innumerable things we need help with, but we especially are looking for help with:

 - legal research in order to fix data errors or other problems (check out the [data-quality label][dq] for some starting points)
 - machine learning or natural language problems. 
 - signal processing to improve the features we can provide for oral argument recordings.
 - test writing -- we always need more and better tests
 - small fixes here and there (these are usually flagged with the [help-wanted label][hw])

But in general, we're looking for all kinds of help! Get in touch if you think you have skills we could use or if you have skills you want to learn by improving CourtListener.

Finally, before we accept code from new people, we ask that they complete a `contributor_license_agreement.txt`. You can find a form to fill out for this in the root of our project. If you have any questions about that, please don't hesitate to ask. The short version is that this helps us to protect the platform.

To familiarize yourself with the state of the art in the technologies we're using,
 we put together the [related academic literature](https://github.com/freelawproject/related-literature) library.


## Upgrading On the Regular

Each day, when you start working on CourtListener, you should make sure that you have the latest code and dependencies. There are a couple different ways to do this. 
 
The first thing you should do is:

    ansible-playbook ansible/upgrade.yml -i ansible/hosts --ask-become-pass
    
This says to run the tasks in the playbook called `upgrade.yml` on the hosts described in `ansible/hosts` (which is localhost). Get the sudo password, since it may be needed to start/stop services. Pretty simple. 

If you're using Vagrant, you also need to be sure to run any new playbooks that were pulled from git in the command above. These will appear in the `ansible` directory for the version of Free Law Machine that you have installed, and represent all the changes that have been made to it since it was created. So, for example, the first time you start up your Vagrant machine, you should run all of the playbooks in the 1.6.0 directory (assuming that's the version you're running):

    ansible-playbook ansible/1.6.0/0001_update_solr.yml -i ansible/hosts --ask-become-pass
    ansible-playbook ansible/1.6.0/0002_create_recap_core.yml -i ansible/hosts --ask-become-pass
    # etc.

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
[trel]: https://trello.com/b/l0qS4yhd/assistance-needed
[hw]: https://github.com/freelawproject/courtlistener/labels/help%20wanted
[dq]: https://github.com/freelawproject/courtlistener/labels/data-quality
[flp]: https://free.law/

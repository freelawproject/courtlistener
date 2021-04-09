# Background

This directory has the nginx configurations and build files for our live site.
Unfortunately, the process for updating and tweaking nginx is a bit wonky. This
could be better, but it's hard b/c of SSL and all the dependencies you have to 
rig up just right to make it work. 

# Tweaks

If you want to test tweaks to the nginx config, you can do so by making your 
changes, and then:

 - Tweak your /etc/hosts to point to www.cl.org
 - Tweak the nginx config to server off of www.cl.org on port 80
 - Remove the other server blocks and the catch all (they use SSL)
 - Tweak the docker-compose file to only have gunicorn and nginx. This will 
 break python. If you need gunicorn to work properly, figure that out and 
 update these notes (sorry). 
 - Build nginx and start it up using the compose file.

#!/bin/bash
# Run this shell script to purge/refresh CL-related Docker images when:
# 1) Merging `main` into a working branch;
# 2) Forking off of `main` to start a new working branch 
# Run it before using the build script. Usage of both of these shell scripts is optional.

# Stop all running Courtlistener cointainers
docker-compose -f  ../courtlistener/docker-compose.yml  down

# Remove any Docker images that are related to Courtlistener
flp_images=`docker image ls | awk '/^freelawproject/{print $1}'`
echo $flp_images
docker image rm --force $flp_images
docker image prune --force

# Pull fresh copies of the Docker images for CL's various services
for image in $flp_images; do
    docker pull $image
done

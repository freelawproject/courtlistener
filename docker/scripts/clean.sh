#!/bin/bash

# Take any running versions down
docker-compose -f  ../courtlistener/docker-compose.yml  down
#
# Now we need to get rid of any images in docker that are related to
# courtlistener
flp_images=`docker image ls | awk '/^freelawproject/{print $3}'`

docker image rm -f $flp_images

echo Y | docker image prune

active=$(docker images --format "{{.Tag}}|{{.Repository}}" | awk -F\| '$1 != "<none>"{print $2}')
for image in $active ; do
    docker pull $image
done

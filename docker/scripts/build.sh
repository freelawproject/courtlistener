#!/bin/sh
#
# Build a Docker image from current code instead of using
# image pulled from external src. Building locally avoids
# issue of checked-out code being ahead of image on Docker Hub 
BUILD_ENV=dev
SHA=`git rev-parse HEAD`
make -e VERSION=${SHA} -f ../django/Makefile development

# start all CL services, with the newly built CL image standing in
# for cl-django image that would otherwise have been pulled from Docker Hub
docker-compose \
	-f ../courtlistener/docker-compose.yml \
       	up -d

# just leaving this in for ease of flipping it on if needed during development
# docker-compose -f ../courtlistener/docker-compose.yml logs

docker exec cl-django python /opt/courtlistener/manage.py makemigrations --check --dry-run
if [ $? != 0 ] ; then
	echo "makemigrations failed on --check"
	exit
fi


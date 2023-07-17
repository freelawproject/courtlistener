#!/bin/sh
#
# Build the docker images
BUILD_ENV=dev
SHA=`git rev-parse HEAD`
make -e VERSION=${SHA} -f ../django/Makefile development
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
docker exec -it cl-doctor pip install x-ray


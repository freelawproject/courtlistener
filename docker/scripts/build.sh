#!/bin/sh
#
# Build the docker images
BUILD_ENV=dev
SHA=`git rev-parse HEAD`
#DJANGO_DOCKER_IMAGE="localhost:5000/freelawproject/courtlistener:latest-web-dev-${SHA}"
#CELERY_DOCKER_IMAGE="localhost:5000/freelawproject/courtlistener:latest-celery-${SHA}"
#export DJANGO_DOCKER_IMAGE CELERY_DOCKER_IMAGE BUILD_ENV
make -e VERSION=${SHA} -f ../django/Makefile development
#docker build --target web-dev --file docker/django/Dockerfile -t ${DJANGO_DOCKER_IMAGE} .
#docker build --target celery --file docker/django/Dockerfile -t ${CELERY_DOCKER_IMAGE} .
#docker push ${DJANGO_DOCKER_IMAGE}
#docker push ${CELERY_DOCKER_IMAGE}
docker network create -d bridge --attachable cl_net_overlay
#cd docker/courtlistener
docker-compose \
	-f ../courtlistener/docker-compose.yml \
       	up -d

docker-compose logs
docker exec cl-django python /opt/courtlistener/manage.py makemigrations --check --dry-run
if [ $? != 0 ] ; then
	echo "makemigrations failed on --check"
	exit 
fi
docker exec -it cl-doctor pip install x-ray


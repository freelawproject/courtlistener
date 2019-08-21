# Run with make push --file docker/django/Makefile
DOCKER_REPOSITORY ?= freelawproject/courtlistener-django

DOCKER ?= docker
export DOCKER

DOCKER_TAG = $(shell cat docker/django/version.txt)

.PHONY: all image push

all: image

image:
	$(DOCKER) build -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) -t $(DOCKER_REPOSITORY):latest --file docker/task-server/Dockerfile .

push: image
	$(DOCKER) push $(DOCKER_REPOSITORY):$(DOCKER_TAG)
	$(DOCKER) push $(DOCKER_REPOSITORY):latest

# Run with make push --file docker/django/Makefile
DOCKER_REPOSITORY ?= freelawproject/courtlistener-django

DOCKER ?= docker
export DOCKER

DOCKER_TAG = $(shell head -1 docker/django/version.txt)

.PHONY: all image push

all: image

image:
	$(DOCKER) buildx create --use
	$(DOCKER) buildx build --platform linux/amd64,linux/arm64 -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) -t $(DOCKER_REPOSITORY):latest --file docker/django/Dockerfile .

push: image
	$(DOCKER) push $(DOCKER_REPOSITORY):$(DOCKER_TAG)
	$(DOCKER) push $(DOCKER_REPOSITORY):latest

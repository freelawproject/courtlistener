# Run with make push --file docker/apache/Makefile
DOCKER_REPOSITORY ?= freelawproject/apache2
DOCKER ?= docker
export DOCKER

DOCKER_TAG = $(shell cat docker/apache/version.txt)

.PHONY: all image push

all: image

image:
	$(DOCKER) build -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) -t $(DOCKER_REPOSITORY):latest --file docker/apache/Dockerfile .

push: image
	$(DOCKER) push $(DOCKER_REPOSITORY):$(DOCKER_TAG)
	$(DOCKER) push $(DOCKER_REPOSITORY):latest

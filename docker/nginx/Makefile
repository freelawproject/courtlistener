# Run with make push --file docker/nginx/Makefile
DOCKER_REPOSITORY ?= freelawproject/nginx
DOCKER ?= docker
export DOCKER

DOCKER_TAG = $(shell cat docker/nginx/version.txt)

.PHONY: all image push

all: image

image:
	$(DOCKER) build -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) -t $(DOCKER_REPOSITORY):latest --file docker/nginx/Dockerfile .

push: image
	$(DOCKER) push $(DOCKER_REPOSITORY):$(DOCKER_TAG)
	$(DOCKER) push $(DOCKER_REPOSITORY):latest

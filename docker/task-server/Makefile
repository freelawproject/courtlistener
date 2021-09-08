# Run with make push --file docker/task-server/Makefile
DOCKER_REPOSITORY ?= freelawproject/task-server

DOCKER ?= docker
export DOCKER

DOCKER_TAG = $(shell head -1 docker/task-server/version.txt)

.PHONY: all image push

all: image

image:
	$(DOCKER) buildx build --platform linux/amd64,linux/arm64 -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --cache-from=type=local,src=cache -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --load --file docker/django/Dockerfile .

push: image
	$(DOCKER) buildx build --push --platform linux/amd64,linux/arm64 -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --file docker/django/Dockerfile .

DOCKER_REPOSITORY ?= freelawproject/courtlistener-testing

DOCKER ?= docker
export DOCKER

DOCKER_TAG = $(shell cat .circleci/version.txt)

.PHONY: all image push

all: image

image:
	$(DOCKER) build -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --file .circleci/Dockerfile .

push: image
	$(DOCKER) push $(DOCKER_REPOSITORY):$(DOCKER_TAG)

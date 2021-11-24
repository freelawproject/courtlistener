# Run with make push --file docker/django/Makefile
# Note that makefiles differentiate between tabs and spaces in a weird way!

DOCKER_REPOSITORY ?= freelawproject/courtlistener-django

DOCKER ?= docker
export DOCKER

DOCKER_TAG = $(shell head -1 docker/django/version.txt)

.PHONY: all image push multiarch_image multiarch_push x86_image x86_push

UNAME := $(shell uname -m)

all: image

image:
	$(DOCKER) build -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) -t $(DOCKER_REPOSITORY):latest --file docker/django/Dockerfile .

push: image
	$(info Checking if valid architecture)
	@if [ $(UNAME) = "x86_64" ]; then \
	    echo "Architecture is OK. Pushing.";\
	    $(DOCKER) push $(DOCKER_REPOSITORY):$(DOCKER_TAG);\
	    $(DOCKER) push $(DOCKER_REPOSITORY):latest;\
	else \
		echo "Only arm64 machines can push single-architecture builds. If you want to \
push a build, try 'make multiarch_push', which builds for both arm64 and amd64. This \
protects against arm64 builds being accidentally deployed to the server (which uses arm64).";\
	fi

multiarch_image:
	export DOCKER_CLI_EXPERIMENTAL=enabled
	$(DOCKER) buildx rm
	$(DOCKER) buildx create --use --name flp-builder
	$(DOCKER) buildx build --platform linux/amd64,linux/arm64 -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --cache-from=type=local,src=cache -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --push --file docker/django/Dockerfile .

multiarch_push: multiarch_image
	$(DOCKER) buildx build --push --platform linux/amd64,linux/arm64 -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --file docker/django/Dockerfile .

x86_image:
	export DOCKER_CLI_EXPERIMENTAL=enabled
	$(DOCKER) buildx rm
	$(DOCKER) buildx create --use --name flp-builder
	$(DOCKER) buildx build --platform linux/amd64 -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --cache-from=type=local,src=cache -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --push --file docker/django/Dockerfile .

x86_push: x86_image
	$(DOCKER) buildx build --push --platform linux/amd64 -t $(DOCKER_REPOSITORY):latest -t $(DOCKER_REPOSITORY):$(DOCKER_TAG) --file docker/django/Dockerfile .

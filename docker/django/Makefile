# Run with VERSION env variable set; e.g. make build-image --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)
# Note that makefiles differentiate between tabs and spaces in a weird way!

# Ensure VERSION is set.
ifndef VERSION
$(error VERSION variable is not set. Use -e VERSION=XYZ to proceed.)
endif

.PHONY: build-image push-image 

REPO ?= freelawproject/courtlistener
DOCKER_TAG_PROD = $(VERSION)-prod
UNAME := $(shell uname -m)

build-image:
	docker build -t $(REPO):$(DOCKER_TAG_PROD) --file docker/django/Dockerfile .

push-image: build-image
	$(info Checking if valid architecture)
	@if [ $(UNAME) != "x86_64" ]; then \
		echo "Only amd64 machines can push single-architecture builds. This \
protects against arm64 builds being accidentally deployed to the server (which uses amd64).";\
		exit 1;
	fi

	    echo "Architecture is OK. Pushing.";\
	    docker push $(REPO):$(DOCKER_TAG_PROD);

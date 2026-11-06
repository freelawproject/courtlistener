# Run with VERSION env variable set; e.g. make build-image --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)
# Note that makefiles differentiate between tabs and spaces in a weird way!

# Ensure VERSION is set.
ifndef VERSION
$(error VERSION variable is not set. Use -e VERSION=XYZ to proceed.)
endif

.PHONY: build-image push-image build-dev-image push-dev-image check-arch

REPO ?= freelawproject/courtlistener
DOCKER_TAG_PROD = $(VERSION)-prod
DOCKER_TAG_DEV = $(VERSION)-dev
UNAME := $(shell uname -m)

build-image:
	docker build -t $(REPO):$(DOCKER_TAG_PROD) --file docker/django/Dockerfile .

# The development image carries the test and lint tooling (BUILD_ENV=dev). The
# compose stack can pull it instead of building it; see
# docker/courtlistener/docker-compose.prebuilt.yml.
build-dev-image:
	docker build -t $(REPO):$(DOCKER_TAG_DEV) -t $(REPO):latest-dev --build-arg BUILD_ENV=dev --file docker/django/Dockerfile .

# Only amd64 machines can push single-architecture builds. This protects
# against arm64 builds being accidentally deployed to the server (which uses
# amd64) or pulled by developers expecting a native amd64 image.
check-arch:
	@if [ $(UNAME) != "x86_64" ]; then \
		echo "Only amd64 machines can push single-architecture builds."; \
		exit 1; \
	fi
	@echo "Architecture is OK."

push-image: build-image check-arch
	docker push $(REPO):$(DOCKER_TAG_PROD)

push-dev-image: build-dev-image check-arch
	docker push $(REPO):$(DOCKER_TAG_DEV)
	docker push $(REPO):latest-dev

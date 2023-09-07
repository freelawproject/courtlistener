# Run with make push --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)
# Note that makefiles differentiate between tabs and spaces in a weird way!

# Ensure VERSION is set.
ifndef VERSION
$(error VERSION variable is not set. Use -e VERSION=XYZ to proceed.)
endif


REPO ?= freelawproject/courtlistener

# The various tags available
DOCKER_TAG_PROD = $(VERSION)-web-prod
WEB_PROD ?= latest-web-prod
CELERY_TAG = $(VERSION)-celery
CELERY_LATEST ?= latest-celery
RSS_TAG ?= $(VERSION)-scrape-rss
RSS_LATEST ?= latest-scrape-rss
WEBHOOKS_TAG ?= $(VERSION)-webhooks-retry
WEBHOOKS_LATEST ?= latest-webhooks-retry

.PHONY: all image push multiarch_image multiarch_push x86_image x86_push

UNAME := $(shell uname -m)

all: image

image:
	docker build --target web-prod -t $(REPO):$(DOCKER_TAG_PROD) -t $(REPO):$(WEB_PROD) --file docker/django/Dockerfile .
	docker build --target celery -t $(REPO):$(CELERY_TAG) -t $(REPO):$(CELERY_LATEST) --file docker/django/Dockerfile .
	docker build --target rss-scraper -t $(REPO):$(RSS_TAG) -t $(REPO):$(RSS_LATEST) --file docker/django/Dockerfile .
	docker build --target retry-webhooks -t $(REPO):$(WEBHOOKS_TAG) -t $(REPO):$(WEBHOOKS_LATEST) --file docker/django/Dockerfile .

push: image
	$(info Checking if valid architecture)
	@if [ $(UNAME) = "x86_64" ]; then \
	    echo "Architecture is OK. Pushing.";\
	    docker push $(REPO):$(DOCKER_TAG_PROD);\
	    docker push $(REPO):$(WEB_PROD);\
	    docker push $(REPO):$(CELERY_TAG);\
	    docker push $(REPO):$(CELERY_LATEST);\
	    docker push $(REPO):$(RSS_TAG);\
	    docker push $(REPO):$(RSS_LATEST);\
	    docker push $(REPO):$(WEBHOOKS_TAG);\
	    docker push $(REPO):$(WEBHOOKS_LATEST);\
	else \
		echo "Only arm64 machines can push single-architecture builds. If you want to \
push a build, try 'make multiarch_push', which builds for both arm64 and amd64. This \
protects against arm64 builds being accidentally deployed to the server (which uses arm64).";\
	fi

multiarch_image:
	export DOCKER_CLI_EXPERIMENTAL=enabled
	docker buildx rm
	docker buildx create --use --name flp-builder
	docker buildx build --platform linux/amd64,linux/arm64 -t $(REPO):$(WEB_PROD) -t $(REPO):$(DOCKER_TAG_PROD) --file docker/django/Dockerfile .
	docker buildx build --platform linux/amd64,linux/arm64 -t $(REPO):$(CELERY_LATEST) -t $(REPO):$(CELERY_TAG) --file docker/django/Dockerfile .
	docker buildx build --platform linux/amd64,linux/arm64 -t $(REPO):$(RSS_TAG) -t $(REPO):$(RSS_LATEST) --file docker/django/Dockerfile .
	docker buildx build --platform linux/amd64,linux/arm64 -t $(REPO):$(WEBHOOKS_TAG) -t $(REPO):$(WEBHOOKS_LATEST) --file docker/django/Dockerfile .

multiarch_push:
	docker buildx build --push --platform linux/amd64,linux/arm64 -t $(REPO):$(WEB_PROD) -t $(REPO):$(DOCKER_TAG_PROD) --file docker/django/Dockerfile .
	docker buildx build --push --platform linux/amd64,linux/arm64 -t $(REPO):$(CELERY_LATEST) -t $(REPO):$(CELERY_TAG) --file docker/django/Dockerfile .
	docker buildx build --push --platform linux/amd64,linux/arm64 -t $(REPO):$(RSS_TAG) -t $(REPO):$(RSS_LATEST) --file docker/django/Dockerfile .
	docker buildx build --push --platform linux/amd64,linux/arm64 -t $(REPO):$(WEBHOOKS_TAG) -t $(REPO):$(WEBHOOKS_LATEST) --file docker/django/Dockerfile .

x86_push:
	export DOCKER_CLI_EXPERIMENTAL=enabled
	docker buildx rm
	docker buildx create --use --name flp-builder
	docker buildx build --push --platform linux/amd64 -t $(REPO):$(WEB_PROD) -t $(REPO):$(DOCKER_TAG_PROD) --file docker/django/Dockerfile .
	docker buildx build --push --platform linux/amd64 -t $(REPO):$(CELERY_LATEST) -t $(REPO):$(CELERY_TAG) --file docker/django/Dockerfile .
	docker buildx build --push --platform linux/amd64 -t $(REPO):$(RSS_TAG)  -t $(REPO):$(RSS_LATEST) --file docker/django/Dockerfile .
	docker buildx build --push --platform linux/amd64 -t $(REPO):$(WEBHOOKS_TAG)  -t $(REPO):$(WEBHOOKS_LATEST) --file docker/django/Dockerfile .

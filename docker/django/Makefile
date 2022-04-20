# Run with make push --file docker/django/Makefile
# Note that makefiles differentiate between tabs and spaces in a weird way!

REPO ?= freelawproject/courtlistener

# The various tags available
VERSION = $(shell head -1 docker/django/version.txt)
DOCKER_TAG_DEV = $(VERSION)-web-dev
DOCKER_TAG_PROD = $(VERSION)-web-prod
WEB_PROD ?= latest-web-prod
WEB_DEV ?= latest-web-dev
CELERY_TAG = $(VERSION)-celery
CELERY_LATEST ?= latest-celery
RSS_TAG ?= latest-scrape-rss

.PHONY: all image push multiarch_image multiarch_push x86_image x86_push

UNAME := $(shell uname -m)

all: image

development:
	docker build --target web-dev -t $(REPO):$(DOCKER_TAG_DEV) -t $(REPO):$(WEB_DEV) --build-arg BUILD_ENV=dev --file docker/django/Dockerfile .
	docker build --target celery -t $(REPO):$(CELERY_TAG) -t $(REPO):$(CELERY_LATEST) --build-arg BUILD_ENV=dev --file docker/django/Dockerfile .

image:
	docker build --target web-prod -t $(REPO):$(DOCKER_TAG_PROD) -t $(REPO):$(WEB_PROD) --file docker/django/Dockerfile .
	docker build --target celery -t $(REPO):$(CELERY_TAG) -t $(REPO):$(CELERY_LATEST) --file docker/django/Dockerfile .
	docker build --target rss-scraper -t $(REPO):$(RSS_TAG) --file docker/django/Dockerfile .

push: image
	$(info Checking if valid architecture)
	@if [ $(UNAME) = "x86_64" ]; then \
	    echo "Architecture is OK. Pushing.";\
	    docker push $(REPO):$(DOCKER_TAG_PROD);\
	    docker push $(REPO):$(DOCKER_TAG_DEV);\
	    docker push $(REPO):$(WEB_PROD);\
	    docker push $(REPO):$(WEB_DEV);\
	    docker push $(REPO):$(CELERY_TAG);\
	    docker push $(REPO):$(CELERY_LATEST);\
	    docker push $(REPO):$(RSS_TAG);\
	else \
		echo "Only arm64 machines can push single-architecture builds. If you want to \
push a build, try 'make multiarch_push', which builds for both arm64 and amd64. This \
protects against arm64 builds being accidentally deployed to the server (which uses arm64).";\
	fi

multiarch_image:
	export DOCKER_CLI_EXPERIMENTAL=enabled
	$(DOCKER) buildx rm
	$(DOCKER) buildx create --use --name flp-builder
	$(DOCKER) buildx build --platform linux/amd64,linux/arm64 -t $(REPO):$(WEB_PROD) -t $(REPO):$(DOCKER_TAG_PROD) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --platform linux/amd64,linux/arm64 -t $(REPO):$(CELERY_LATEST) -t $(REPO):$(CELERY_TAG) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --platform linux/amd64,linux/arm64 -t $(REPO):$(RSS_TAG) -t $(REPO):$(CELERY_TAG) --file docker/django/Dockerfile .

multiarch_push:
	$(DOCKER) buildx build --push --platform linux/amd64,linux/arm64 -t $(REPO):$(WEB_PROD) -t $(REPO):$(DOCKER_TAG_PROD) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --push --platform linux/amd64,linux/arm64 -t $(REPO):$(CELERY_LATEST) -t $(REPO):$(CELERY_TAG) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --push --platform linux/amd64,linux/arm64 -t $(REPO):$(RSS_TAG) --file docker/django/Dockerfile .

x86_push:
	export DOCKER_CLI_EXPERIMENTAL=enabled
	$(DOCKER) buildx rm
	$(DOCKER) buildx create --use --name flp-builder
	$(DOCKER) buildx build --push --platform linux/amd64 -t $(REPO):$(WEB_PROD) -t $(REPO):$(DOCKER_TAG_PROD) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --push --platform linux/amd64 -t $(REPO):$(CELERY_LATEST) -t $(REPO):$(CELERY_TAG) --file docker/django/Dockerfile .
	$(DOCKER) buildx build --push --platform linux/amd64 -t $(REPO):$(RSS_TAG) --file docker/django/Dockerfile .

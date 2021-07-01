.PHONY: all build-all-images build-ds push-images

# default tag, used to tag images
# we use latest as default, for convenience
export TAG ?= latest

REVISION ?= $(shell git rev-parse HEAD)

# where to push docker images
CONTAINER_REPO=eu.gcr.io/objectiv-production

# by default we build all images
all: build-all-images

# what to build
build-all-images: build-backend build-ds

# ds images, build jupyter notebook with DB requirements
build-ds: build-ds-notebook

# what images to push
push-images: push-image-backend push-image-notebook

# images are pushed, tagged both "latest" and $REVISION
push-image-%:
	$(eval MODULE = $(subst push-image-,,$@))
	$(eval URL=$(CONTAINER_REPO)/$(MODULE))
	docker tag objectiv/$(MODULE):$(TAG) $(URL):latest
	docker push $(URL)
	gcloud container images add-tag --quiet $(URL):latest $(URL):$(REVISION)


## build backend images
build-backend:
	cd backend && make docker-image

build-ds-notebook:
	cd ds && \
	docker build \
	-t objectiv/notebook:$(TAG) -f docker/notebook/Dockerfile .


build-tracker:
	cd tracker && yarn install && yarn build

publish-tracker: build-tracker
	cd tracker/verdaccio && make run 
	cd tracker && yarn publish

# control stack through docker-compose
start:
	docker-compose up -d

stop:
	docker-compose down

update:
	docker-compose up -d --no-deps

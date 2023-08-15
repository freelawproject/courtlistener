#!/bin/bash
# Run this shell script to rm existing CL Docker images and pull the latest, freshest ones.
# Use when:
## 1) Merging `main` into a working branch;
## 2) Forking off of `main` to start a new working branch

# Mostly from here: https://stackoverflow.com/a/39127792/3256077

# stop all running CL containers
docker-compose -f ../courtlistener/docker-compose.yml stop
# rm said containers
docker-compose -f ../courtlistener/docker-compose.yml rm --force
# rm the locally-stored CL images themselves
docker rmi $(docker compose --file ../courtlistener/docker-compose.yml config --images)
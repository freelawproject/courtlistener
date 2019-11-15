name: docker build and test

on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Make solr dir and move to it
        run: mkdir courtlistner-solr-server && cd courtlistener-solr-server
      - name: Check out solr
        uses: actions/chcekout@v1
        with:
          repository: freelawproject/courtlistener-solr-server
      - name: make courtlistener dir and move to it
        run: cd .. && mkdir courtlistener && cd courtlistneer
      - name: Check out CourtListener
        uses: actions/checkout@v1
      - name: Start docker compose
        run: cd docker/courtlistener && docker-compose up -d
        

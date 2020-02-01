# Push new image with:

1. Updating version.txt

1. Changing into the root directory, and then doing:

        make push --file docker/django/Makefile
        
# Build only with:

     make image --file docker/django/Makefile
     
Or :
    
    docker build --tag=freelawproject/courtlistener-django:latest --file docker/django/Dockerfile .

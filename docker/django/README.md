# Before you build

1. Remember to log into docker with `docker login` command

# Push new image with:

1. Updating version.txt

1. Changing into the root directory, and then doing:

        make push --file docker/django/Makefile

# Build only with:

     make image --file docker/django/Makefile

Or :

    docker build --tag=freelawproject/courtlistener-django:latest --file docker/django/Dockerfile .

 
# In Practice

1. It is convenient to deploy both django and task-server together.  
2. That can be accomplished by updating both version.txt files.
3. Then running the following command to build and deploy both.


    make push --file docker/django/Makefile && make push --file docker/task-server/Makefile

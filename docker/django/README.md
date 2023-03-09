# Before you build and push

1. Remember to log into docker with `docker login` command

1. Figure out if you need to make a multi-architecture image or just an `amd64` image.

    - Run `uname -m` to figure out if you have an `arm64` or `x86_64` architecture.

    - If you're on an `x86_64` machine, just make a single-architecture build. Skip to the next section.

    - If you're on an `arm_64` machine, you have three options:

      1. Build a single-architecture `arm64` build for your own local development
      2. Build a single-architecture `x86_64` build that you can push to docker hub (it won't work for you locally, of course)
      3. Build a multi-architecture `arm64`/`x86_64` build for both local development and to push to docker hub. These take longest to build, but can serve both purposes.

1. Multi-architecture and `x86_64` images can be pushed to docker hub. `arm64` images cause a lot of trouble if they are deployed to the server and thus should only be pushed without the `latest` tag.


# Build can be done with:

Change to the root directory and run one of:

    # Make a single-architecture build in the same architecture as your
    # computer (great for normal dev)
    make image --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)

    # Make a multi-architecture build
    make multiarch_image --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)

    # Make an x86_64 build from an arm64 computer
    make x86_image --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)

# Push new image with:

Change into the root directory, and then run one of:

    # Push a single-architecture x86 build from an x86 machine
    make push --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)

    # Push a multi-architecture build
    make multiarch_push --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)

    # Push an x86_64 build from an arm64 computer
    make x86_push --file docker/django/Makefile -e VERSION=$(git rev-parse --short HEAD)

Each of the above will build the image if it's not already built.


# In Practice

1. Docker images are usually made by our continuous deployment pipeline.

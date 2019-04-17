# This image is used by CircleCI to run tests.
# It's published as freelawproject/courtlistener-testing:x.y.z.

FROM ubuntu:trusty

# Establish noninteractive environment
#   This prevents some warnings for packages that have configuration
#   prompts as part of their installation.
ENV DEBIAN_FRONTEND=noninteractive

# Copy over required files.
COPY .circleci /var/circleci
COPY requirements.txt requirements-test.txt /tmp/

RUN /var/circleci/configure-postgres.sh && \
    /var/circleci/configure-redis.sh && \
    /var/circleci/configure-courtlistener.sh

ENTRYPOINT ["/var/circleci/activate.sh"]

# This image is used by CircleCI to run tests.
# It's published as freelawproject/courtlistener-testing:x.y.z.

FROM ubuntu:trusty

RUN apt-get update -qq && \
  apt-get install -qq software-properties-common git && \
  apt-add-repository ppa:ansible/ansible -y && \
  apt-get update -qq && \
  apt-get install -qq ansible

COPY ansible /var/ansible
RUN /var/ansible/./test.yml -i /var/ansible/hosts

COPY .circleci/activate.sh /usr/local/bin/activate.sh
ENTRYPOINT ["/usr/local/bin/activate.sh"]

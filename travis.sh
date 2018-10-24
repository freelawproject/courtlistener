#!/bin/bash
set -e

if [[ -z $1 ]]; then
  "I need a command!"
  exit 1
fi

case "$1" in
  install_ansible)

    sudo apt-get update -qq \
      && sudo apt-get install -qq software-properties-common \
      && sudo apt-add-repository ppa:ansible/ansible -y \
      && sudo apt-get update -qq \
      && sudo apt-get install -qq ansible

    ;;

  purge_postgres)
    # Remove various pre-installed postgres packages so we can ensure a specific version.

    sudo /etc/init.d/postgresql stop
    sudo apt-get --purge remove -qq postgresql\*
    sudo rm -fr /etc/postgresql /etc/postgresql-common /var/lib/postgresql
    sudo userdel -r postgres || true
    sudo groupdel postgres || true

    ;;

  *)
    echo "Unknown command $1"
    exit 2
esac

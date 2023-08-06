#!/bin/sh


if [ "$1" = 'restart' ] ; then
    docker-compose -f ../courtlistener/docker-compose.yml restart
fi
set -e
docker exec -it cl-django git config --global --add safe.directory /opt/courtlistener
docker exec -it cl-django pre-commit run --all-files
docker exec -it cl-django mypy \
  --follow-imports=skip \
  --exclude 'migrations/*' \
  -p cl.alerts \
  -p cl.audio \
  -p cl.citations \
  -p cl.corpus_importer \
  -p cl.lib \
  -p cl.opinion_page \
  -p cl.recap_rss \
  -p cl.settings \
  -p cl.simple_pages
docker exec -it cl-django mypy \
  --follow-imports=skip \
  --exclude 'migrations/*' \
  cl/api/api_permissions.py \
  cl/api/management/commands/cl_retry_webhooks.py \
  cl/api/models.py \
  cl/api/routers.py \
  cl/api/tasks.py \
  cl/api/tests.py \
  cl/api/utils.py \
  cl/api/views.py \
  cl/api/webhooks.py \
  cl/donate/management/commands/charge_monthly_donors.py \
  cl/donate/utils.py \
  cl/tests/utils.py \
  cl/users/email_handlers.py \
  cl/users/forms.py \
  cl/users/management/commands/cl_account_management.py \
  cl/users/management/commands/cl_delete_old_emails.py \
  cl/users/management/commands/cl_retry_failed_email.py \
  cl/users/tasks.py \
  cl/recap/management/commands/remove_appellate_entries_with_long_numbers.py
docker exec -it cl-django    flynt . --line-length=79 --transform-concats --fail-on-change
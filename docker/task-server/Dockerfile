#Inherit our django image which has the same pip requirements start the celery container.
FROM freelawproject/courtlistener-django:bte_beta38

WORKDIR /usr/src/app

## Needs to be two commands so second one can use variables from first.
ENV \
    CELERY_TASKS_DIR=/opt/celery \
    CELERY_USER_ID=33
ENV \
    PYTHONPATH="${PYTHONPATH}:${CELERY_TASKS_DIR}"

USER ${CELERY_USER_ID}

CMD celery \
    --app=cl worker \
    --loglevel=info \
    --events \
    --concurrency=4 \
    --pool=prefork \
    --queues=io_bound,celery


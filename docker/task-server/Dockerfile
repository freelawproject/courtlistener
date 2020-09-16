FROM python:2.7

WORKDIR /usr/src/app

# Use lots of layers. Bigger image, but faster builds. Slow stuff is up here at
# the top.
RUN apt-get update

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt && \
    pip install --no-cache-dir -r requirements.txt

COPY requirements-flp.txt ./
RUN pip install --no-cache-dir -r requirements-flp.txt


## Needs to be two commands so second one can use variables from first.
ENV \
    CELERY_TASKS_DIR=/opt/celery \
    CELERY_USER_ID=33
ENV \
    PYTHONPATH="${PYTHONPATH}:${CELERY_TASKS_DIR}"

RUN mkdir /var/log/courtlistener && \
    chmod 777 /var/log/courtlistener

USER ${CELERY_USER_ID}

CMD celery \
    --app=cl worker \
    --loglevel=info \
    --events \
    --concurrency=4 \
    --pool=prefork \
    --queues=io_bound,celery


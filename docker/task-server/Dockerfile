FROM python:2.7

WORKDIR /usr/src/app

# Use lots of layers. Bigger image, but faster builds. Slow stuff is up here at
# the top.
RUN apt-get update --option "Acquire::Retries=3" --quiet=2 && \
    apt-get install -y --no-install-recommends apt-utils && \
    apt-get install \
        --option "Acquire::Retries=3" \
        --no-install-recommends \
        --assume-yes \
        --quiet=2 \
        antiword imagemagick libav-tools libffi-dev \
        libtiff5-dev libwpd-tools libxml2-dev libxslt-dev poppler-utils \
        python-dev

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install git+https://github.com/freelawproject/judge-pics@master


## Needs to be two commands so second one can use variables from first.
ENV \
    CELERY_TASKS_DIR=/opt/celery \
    CELERY_USER=celery
ENV \
    PYTHONPATH="${PYTHONPATH}:${CELERY_TASKS_DIR}"

RUN addgroup --gid 3502 web-assets && \
    adduser --disabled-password --system --ingroup web-assets ${CELERY_USER} && \
    mkdir /var/log/courtlistener && \
    chmod 777 /var/log/courtlistener

USER ${CELERY_USER}

CMD celery \
    --app=cl worker \
    --loglevel=info \
    --events \
    --concurrency=1 \
    --pool=prefork \
    --queues=io_bound,celery

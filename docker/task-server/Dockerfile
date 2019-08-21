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
        antiword docx2txt ghostscript imagemagick libav-tools libffi-dev \
        libwpd-tools libxml2-dev libxslt-dev poppler-utils \
        python-dev tesseract-ocr

# Install Tesseract 4
RUN echo "deb http://deb.debian.org/debian stretch-backports main" > \
      /etc/apt/sources.list.d/backports.list && \
    apt-get update && \
    apt-get install -t stretch-backports -y tesseract-ocr tesseract-ocr-eng

COPY requirements.txt requirements-flp.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install git+https://github.com/freelawproject/judge-pics@master && \
    update-seals -f
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
    --concurrency=1 \
    --pool=prefork \
    --queues=io_bound,celery

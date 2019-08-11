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
        libffi-dev libwpd-tools libxml2-dev libxslt-dev poppler-utils \
        python-dev

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install git+https://github.com/freelawproject/judge-pics@master && \
    update-seals -f

ENV \
    PYTHONPATH="${PYTHONPATH}"

RUN mkdir /var/log/courtlistener && \
    chmod 777 /var/log/courtlistener

CMD python /opt/courtlistener/manage.py runserver 0.0.0.0:8000

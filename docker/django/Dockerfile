FROM python:3.8

WORKDIR /usr/src/app

# Use lots of layers. Bigger image, but faster builds. Slow stuff is up here at
# the top.

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt && \
    pip install --no-cache-dir -r requirements.txt

COPY requirements-flp.txt ./
RUN pip install --no-cache-dir -r requirements-flp.txt
ENV \
    PYTHONPATH="${PYTHONPATH}"

RUN mkdir /var/log/courtlistener && \
    chmod 777 /var/log/courtlistener

CMD python /opt/courtlistener/manage.py runserver 0.0.0.0:8000

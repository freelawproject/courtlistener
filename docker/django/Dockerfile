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
        `# Document extraction and OCR tools` \
        antiword docx2txt ghostscript libwpd-tools poppler-utils \
        `# Audio extraction/manipulation tools` \
        libav-tools \
        `# Image tweaking tools` \
        imagemagick \
        `# Other dependencies` \
        libffi-dev libxml2-dev libxslt-dev \
        python-dev

# Install Tesseract 4
RUN echo "deb http://deb.debian.org/debian stretch-backports main" > \
      /etc/apt/sources.list.d/backports.list && \
    apt-get update && \
    apt-get install -t stretch-backports -y tesseract-ocr tesseract-ocr-eng


COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install git+https://github.com/freelawproject/judge-pics@master && \
    update-seals -f

ENV \
    PYTHONPATH="${PYTHONPATH}"

RUN mkdir /var/log/courtlistener && \
    chmod 777 /var/log/courtlistener

CMD python /opt/courtlistener/manage.py runserver 0.0.0.0:8000

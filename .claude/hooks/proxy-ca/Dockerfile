# A stack base image rebuilt to trust a TLS-intercepting proxy's CA.
#
# session_start.py builds this from each Docker Hub base image the stack
# uses, with a directory holding the host's CA bundle as the build context,
# and the docker-compose.yml beside this file swaps the results in. uv and
# npm ship their own root certificates, so both are pointed at the system
# store, which the images built on top of this inherit.
ARG BASE
FROM ${BASE}
COPY ca-bundle.crt /usr/local/share/ca-certificates/proxy-ca-bundle.crt
RUN update-ca-certificates
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    NPM_CONFIG_CAFILE=/etc/ssl/certs/ca-certificates.crt

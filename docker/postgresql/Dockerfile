ARG POSTGRES_VERSION
FROM postgres:${POSTGRES_VERSION}

# Install openssl
RUN apk --update add openssl

# Script that generates SSL certificate and run PostgreSQL
ADD docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["sh", "/docker-entrypoint.sh"]

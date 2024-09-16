ARG POSTGRES_VERSION
FROM postgres:${POSTGRES_VERSION}

# Create the 'etc/ssl/private' directory
RUN mkdir -p /etc/ssl/private

# Set permissions to the folder
RUN chown -R postgres:postgres /etc/ssl/private && chmod -R 0700 /etc/ssl/private

# Copy the certificate and private key to the directory container
COPY ./cl-postgres.crt /etc/ssl/private/cl-postgres.crt
COPY ./cl-postgres.key /etc/ssl/private/cl-postgres.key

# Set access rights to the certificate and private key
RUN chown postgres:postgres /etc/ssl/private/cl-postgres.* && chmod 0600 /etc/ssl/private/cl-postgres.*

FROM nginx:1.19.3

# Delete some of the standard stuff from the image
RUN rm /etc/nginx/conf.d/default.conf && rm -r /docker-entrypoint.d/

# And replace it
COPY docker/nginx/nginx.conf        /etc/nginx
COPY docker/nginx/sites-available/  /etc/nginx/sites-available/
COPY docker/nginx/sites-enabled/    /etc/nginx/sites-enabled/
COPY docker/nginx/includes          /etc/nginx/includes/

# This image extends our base docker image and adds Apache to it
# Expectations:
#  - Mount your encryption certs into /etc/letsencrypt/
#  - Mount code into /opt/courtlistener
#  - Python code in /usr/local/lib/python3.8/site-packages/
#  - Media files symbolically linked into /var/www/cl/cl/assets/static/
#  - Exposed ports on 80 and 443.
#
# An example run command might be:
#
#  docker run -ti --rm \
#    # If you want to map it to a higher port for development:
#    -p 8000:80 \
#    # If you want it to have a name for easy debugging:
#    --name apache \
#    # Mount the code and certs (read-only):
#    -v /home/mlissner/Programming/courtlistener/:/opt/courtlistener \
#    -v /etc/letsencrypt:/etc/letsencrypt:ro
#    freelawproject/apache2:latest
#
# Things that get done for you:
#  - Sites get COPY'ed into /etc/apache2/sites-available and are a2ensite'd
#    from there. You could try to do this at runtime via a mount, but you'd
#    still have to a2ensite if you did it that way, so better to do it in the
#    build stage.
#  - The "worker" MPM is enabled and configured according to the settings in
#    mpm_worker.conf
#  - Apache is optimized to use only the modules it needs.
#  - Apache logs are sent to stdout so they can be captured by docker.
#  - Apache is set up in worker MPM mode and WSGI in daemon mode, as described
#    here: http://blog.dscpl.com.au/2012/10/why-are-you-using-embedded-mode-of.html
#
FROM freelawproject/courtlistener-django:latest

RUN apt-get update --option "Acquire::Retries=3" --quiet=2 \
  && apt-get install \
        --no-install-recommends \
        --assume-yes \
        --quiet=2 \
        # Apache
        apache2 \
        # Extra Apache modules & tools
        apache2-dev libapache2-mod-xsendfile locales wget \
  # Enable our locale and generate it.
  && sed -i 's/^# *\(en_US.UTF-8\)/\1/' /etc/locale.gen \
  && locale-gen

# Install mod_wsgi manually. This is necessary because the version that comes
# with Ubuntu will only link against the default version of Python, which is
# not what we use. Get the latest version from:
#
#   https://github.com/GrahamDumpleton/mod_wsgi/releases
#
# Instructions here:
#
#   https://modwsgi.readthedocs.io/en/develop/user-guides/quick-installation-guide.html
#
# And test after upgrading that the correct version of Python is used by using
# the python_version_test.py WSGI file.
RUN wget https://codeload.github.com/GrahamDumpleton/mod_wsgi/tar.gz/4.7.1 --output-document mod_wsgi.tar.gz \
  && tar -x -f mod_wsgi.tar.gz \
  && cd mod_wsgi-4.7.1/ \
  && ./configure && make && make install && make clean && make distclean \
  && echo "LoadModule wsgi_module /usr/lib/apache2/modules/mod_wsgi.so" >> /etc/apache2/mods-available/wsgi.load
RUN apt-get purge --assume-yes --quiet=2 --auto-remove apache2-dev wget

# With mod_wsgi in place, set up the modules
COPY docker/apache/mods-available/mpm_worker.conf /etc/apache2/mods-available/mpm_worker.conf
RUN a2dismod mpm_event && \
  a2enmod \
    # Keep all static modules; they're compiled in
    # Used for  <Directory>, <Files>, and <Location> and .htaccess files.
    access_compat \
    # Dependency for access_compat
    authn_core \
    # We use this from time to time to redirect traffic
    alias \
    # Needed for authz_host. Keep
    authz_core \
    # Dependency for the status module. Keep.
    authz_host \
    # Needed to ls directories
    autoindex \
    # Zips HTML and whatnot before serving
    deflate \
    # Used to add slashes to URLs and to serve index.html files
    dir \
    # Allows env vars to be used. I'm not sure if Ubuntu uses these
    env \
    # Required by deflate
    filter \
    # Used to set headers
    headers \
    # Used to set default charset
    mime \
    # Worker module
    mpm_worker \
    # Does content negotiation
    negotiation \
    # Does reverse proxying for Matomo
    proxy \
    # Does proxying
    proxy_http \
    # For redirecting during big traffic
    rewrite \
    # Needed for ssl
    setenvif \
    # Shares memory?
    slotmem_shm \
    # Another shared memory cache. Not messing with this.
    socache_shmcb \
    # For ssl
    ssl \
    # For monitoring
    status \
    # For WSGI. Keep.
    wsgi \
    # For sending files. Keep.
    xsendfile && \
  a2dismod \
    # Need to use this or else it gives dumb warnings
    -f \
    # Used for basic auth
    auth_basic \
    # Used for special access to files
    authn_file \
    # Needed for local user access permissions
    authz_user \
    # We don't use CGI for anything
    cgid \
    # Does Apache JServ Protocol version 1.3
    proxy_ajp \
    # For load balancing
    proxy_balancer \
    # For connect protocol?
    proxy_connect

# Use this pattern to add global configurations
# 1. This stops the warning about the servername being unset.
RUN echo "ServerName courtlistener.com" >> /etc/apache2/conf-available/fqdn.conf && \
  a2enconf fqdn

# Set up the sites
COPY docker/apache/sites-available/* /etc/apache2/sites-available/
WORKDIR /etc/apache2/sites-available
RUN a2ensite * && \
  a2dissite 000-default.conf default-ssl.conf

# https://httpd.apache.org/docs/2.4/stopping.html#gracefulstop
# Do a graceful shutdown with: kill -SIGWINCH pid
STOPSIGNAL SIGWINCH

COPY docker/apache/apache2-foreground /usr/local/bin/

EXPOSE 80
EXPOSE 443
CMD ["apache2-foreground"]

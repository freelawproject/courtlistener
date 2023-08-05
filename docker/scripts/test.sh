
docker exec cl-doctor pip install x-ray
docker exec -e SELENIUM_DEBUG=1 -e SELENIUM_TIMEOUT=30 cl-django python /opt/courtlistener/manage.py test cl --verbosity=2 --exclude-tag selenium --parallel
docker exec -e SELENIUM_DEBUG=1 -e SELENIUM_TIMEOUT=120 cl-django python /opt/courtlistener/manage.py test cl --verbosity=2 --tag selenium --parallel


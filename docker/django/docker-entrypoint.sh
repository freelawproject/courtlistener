#!/bin/sh
set -e

case "$1" in
'celery')
    exec celery \
        --app=cl worker \
        --loglevel=info \
        --events \
        --pool=prefork \
        --hostname=prefork@%h \
        --queues=${CELERY_QUEUES} \
        --concurrency=${CELERY_PREFORK_CONCURRENCY:-0} \
        --prefetch-multiplier=${CELERY_PREFETCH_MULTIPLIER:-1}
    ;;
'web-dev')
    python /opt/courtlistener/manage.py migrate
    python /opt/courtlistener/manage.py createcachetable
    exec python /opt/courtlistener/manage.py runserver 0.0.0.0:8000
    ;;
'web-prod')
    # Tips:
    # 1. Set high number of --workers. Docs recommend 2-4× core count
    # 2. Set --limit-request-line to high value to allow long Solr queries
    # 3. Set --max-requests to reset each worker once in a while
    exec gunicorn cl.asgi:application \
        --chdir /opt/courtlistener/ \
        --user www-data \
        --group www-data \
        --workers ${NUM_WORKERS:-48} \
        --worker-class cl.workers.UvicornWorker \
        --limit-request-line 6000 \
        --timeout 180 \
        --bind 0.0.0.0:8000
    ;;
'rss-scraper')
    exec /opt/courtlistener/manage.py scrape_rss
    ;;
'retry-webhooks')
    exec /opt/courtlistener/manage.py cl_retry_webhooks
    ;;
*)
    echo "Unknown command"
    ;;
esac

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
    ./manage.py migrate
    ./manage.py createcachetable
    exec ./manage.py runserver 0.0.0.0:8000
    ;;
'web-prod')
    # Tips:
    # 1. Set high number of --workers. Docs recommend 2-4× core count
    # 2. Set --limit-request-line to high value to allow long search queries
    # 3. --max-requests is per worker, so if you see log lines about things
    #    being reset for this reason, that doesn't mean the pod is unavailable.
    exec gunicorn cl.asgi:application \
        --chdir /opt/courtlistener/ \
        --user www-data \
        --group www-data \
        --workers ${NUM_WORKERS:-48} \
        --worker-class cl.workers.UvicornWorker \
        --limit-request-line 6000 \
        --timeout 180 \
        --max-requests ${MAX_REQUESTS:-2500} \
        --max-requests-jitter 100 \
        --bind 0.0.0.0:8000
    ;;
'rss-scraper')
    exec ./manage.py scrape_rss
    ;;
'retry-webhooks')
    exec ./manage.py cl_retry_webhooks
    ;;
'sweep-indexer')
    exec ./manage.py sweep_indexer
    ;;
'probe-iquery-pages-daemon')
    exec ./manage.py probe_iquery_pages_daemon
    ;;
'cl-send-rt-percolator-alerts')
    exec ./manage.py cl_send_rt_percolator_alerts
    ;;
*)
    echo "Unknown command"
    ;;
esac

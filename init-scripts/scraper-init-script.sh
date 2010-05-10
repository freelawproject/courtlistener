#!/bin/bash

case "${1:-''}" in
  'start')
           echo -n "Starting the scraper...."
           su - www-data -c '/usr/bin/python /home/mlissner/FinalProject/alert/scrape_and_parse.py -d' &
           sleep 1
           echo "Done"
        ;;
  'stop')
           echo -n "Killing the scraper..."
           sleep 1
           # this is a mess. Basically, it finds the scraper's pid, and feeds that to kill with signal 2.
           kill -2 `ps -eo pid,command | grep 'scrape_and_parse.py -d' | grep -v 'grep' | awk -F' ' '{print $1}';`
           echo "Done"
        ;;
  'restart')
           # Kill, then start it again.
           echo -n "Killing the scraper..."
           kill -2 `ps -eo pid,command | grep 'scrape_and_parse.py -d' | grep -v 'grep' | awk -F' ' '{print $1}';`
           sleep 1
           echo "Dead"
           echo -n "Restarting the scraper...."
           su - www-data -c '/usr/bin/python /home/mlissner/FinalProject/alert/scrape_and_parse.py -d' &
           sleep 1
           echo "Done"
        ;;
  *)      # no parameter specified
        echo "Usage: $SELF start|stop|restart"
        exit 1
        ;;
esac

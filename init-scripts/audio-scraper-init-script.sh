#!/bin/bash

# import the settings we need, and make some useful variables.
INSTALL_ROOT=`python -c "import sys; sys.path.append('../alert/'); import settings; print settings.INSTALL_ROOT"`
SCRAPER_LOCATION=$INSTALL_ROOT\alert/scrape_and_encode_audio.py

case "${1:-''}" in
  'start')
           echo -n "Starting the audio scraper...."
           su - www-data -c "/usr/bin/python $SCRAPER_LOCATION -d" &
           echo $$ > /tmp/scraper.pid
           sleep 1
           echo "Done"
        ;;
  'stop')
           echo -n "Killing the scraper..."
           sleep 1
           # this is a mess. Basically, it finds the scraper's pid, and feeds that to kill with signal 2.
           kill -2 `ps -eo pid,command | grep 'scrape_and_encode_audio.py -d' | grep -v 'grep' | awk -F' ' '{print $1}';`
           rm /tmp/scraper.pid
           echo "Done"
        ;;
  'restart')
           # Kill, then start it again.
           echo -n "Killing the scraper..."
           kill -2 `ps -eo pid,command | grep 'scrape_and_encode_audio.py -d' | grep -v 'grep' | awk -F' ' '{print $1}';`
           rm /tmp/scraper.pid
           sleep 1
           echo "Dead"
           echo -n "Restarting the scraper...."
           su - www-data -c "/usr/bin/python $SCRAPER_LOCATION -d" &
           echo $$ > /tmp/scraper.pid
           sleep 1
           echo "Done"
        ;;
  *)      # no parameter specified
        echo "Usage: $SELF start|stop|restart"
        exit 1
        ;;
esac

#!/bin/bash
# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.

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

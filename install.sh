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

# This script is designed to install the CourtListener project on a Linux
# machine. It has been tested on Ubuntu 10.04, 10.10, 11.04 and 11.10.
#
# This script should also serve as the documentation for the installation
# process.

# This script does the following:
# - check for and install its own dependencies (such as aptitude, hg, svn, etc)
# - get various input from the user.
# - install django from source
# - install CourtListener from source
# - put some basic data in the database
# - install & configure Solr
# - install haystack
# - configure mysql & courtlistener
# - install django-celery, celery and rabbitmq
# - install the django-debug toolbar
# - install the south DB migration tool
# - sync the django configuration with the database
# - exit

# It's a monster...hopefully one that works.


function print_help {
cat <<EOF
NAME
    install.sh

SYNOPSIS
    install.sh --help | --install | --lightlyTestedOption

OPTIONS
    This program will install the courtlistener software on your computer. It
    makes a number of assumptions, but does its best. Patches and contributions
    are welcome.

    Standard Options
    --help      Print this help file
    --install   Install all components of the courtlistener software

    Lightly Tested Options
    --check_deps
            Verify that the required dependencies are installed.
    --mysql
            Configure the MySQL database
    --ffmpeg
            install the FFmpeg audio transcoding library from source
    --solr
            install the Solr search engine
    --django
            install Django
    --courtlistener
            set up the CL repository, and configure it with django
    --importdata
            import some basic data into the DB, setting up the courts
    --debugtoolbar
            install the django debug toolbar
    --djangocelery
            install django-celery to handle task queues
    --haystack
            install the Haystack connector
    --djangoextensions
            install the django-extensions package from github
    --south
            install the South DB migration tool from mercurial
    --finalize
            finalize the installation

EXIT STATUS
    0   The installation was successful.
    >0  An error occured, as follows:
        1   Unknown error
        2   Invalid usage
        3   Missing critical dependency
        4   Error installing django from source
        5   Error getting user input
        6   Error installing Solr
        7   Error configuring MySQL

AUTHOR AND COPYRIGHT
    This script was authored by Michael Lissner and is released under the same
    permissive license as the remainder of the CourtListener program.

EOF
}


function get_user_input {
cat<<EOF
Welcome to the install script. This script will install the CourtListener system
on your Debian-based Linux computer. We will begin by gathering several pieces
of input from you, and then we will install everything that's needed.

EOF
    read -p "Shall we continue? (y/n): " proceed
    if [ $proceed != 'y' ]
    then
        exit 2
    else
        sleep 0.5
        echo -e "\nGreat. Off we go.\n"
    fi

    # this function sets some variables that will be used throughout the program
    read -p "The default location for your django installation is /usr/local/django. Is this OK? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        read -p "Where shall we install django (starting at /, no trailing slash)?: " DJANGO_INSTALL_DIR
    else
        DJANGO_INSTALL_DIR='/usr/local/django'
    fi

    # set up the PYTHON_SITES_PACKAGES_DIR
    PYTHON_SITES_PACKAGES_DIR=`python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"`
    read -p "The default location for your CourtListener installation is /var/www. Is this OK? (y/n): " proceed
    if [ $proceed == 'n' ]
    then
        read -p "You will need to update the init scripts manually to point to this location. Where shall we install CourtListener (starting at /, no trailing slash): " CL_INSTALL_DIR
    else
        CL_INSTALL_DIR='/var/www'
    fi

    # set up the private settings file
    echo -e "\nWe are going to set up two settings files. One with private data, and one with
public data. For the private data, we will need to gather some information.
This file should NEVER be checked into revision control!
"
    read -p "What name would you like used as the admin name for the site (e.g. Michael Lissner): " CONFIG_NAME
    read -p "What email address should be used for the admin of the site (e.g. mike@courtlistener.com): " CONFIG_EMAIL
    read -p "Would you like the django-debug toolbar installed? It's good for dev work. (y/n): " INSTALL_DEBUG_TOOLBAR
    read -p "Would you like the django-extensions package installed? It's also good for dev work. (y/n): " INSTALL_DJANGO_EXTENSIONS
    read -p "Is this a development machine? (y/n): " DEVELOPMENT
    if [ $DEVELOPMENT == 'y' ]
    then
        DEVELOPMENT=true
    else
        DEVELOPMENT=false
    fi
    echo -e "\nGreat. These are stored in a tuple in the 20-private.conf file. You can add more
people and other settings manually, if you like.
\nMANAGERS is set equal to the admins.
DEBUG is set to True.
CACHE_BACKEND is not set (which is fine for a dev machine).
EMAIL_BACKEND is set to Console (for a production machine, this should be changed)
TEMPLATE_DEBUG is set to DEBUG.
DEVELOPMENT is set to $DEVELOPMENT
TIME_ZONE is set to America/Los Angeles
"

    # set up the MySQL configs
    read -p "We will be setting up a MySQL DB. What would you like its name to be (e.g. courtlistener): " MYSQL_DB_NAME
    read -p "And we will be giving it a username which must be different than the DB name. What would you like that to be (e.g. django): " MYSQL_USERNAME
    MYSQL_PWD=`python -c 'from random import choice; print "".join([choice("abcdefghijklmnopqrstuvwxyz0123456789") for i in range(50)]);'`
    echo -e "\nYou can set up the MySQL password manually, but we recommend a randomly
generated password, since you should not ever need to type it in.
"
    read -p "Use the following random password: '$MYSQL_PWD'? (y/n): " proceed
    if [ $proceed == 'n' ]
    then
        read -p "Very well. What would you like the password to be (do not use the # symbol): " MYSQL_PWD
    fi

    CELERY_PWD=`python -c 'from random import choice; print "".join([choice("abcdefghijklmnopqrstuvwxyz0123456789") for i in range(50)]);'`
    echo -e "\nFinally, we will be installing Celery, which requires a password as well.
You can set up the Celery password manually, but we recommend a randomly
generated one, since you should not ever need to type it in.
"
    read -p "Use the following random password: '$CELERY_PWD'? (y/n): " proceed
    if [ $proceed == 'n' ]
    then
        read -p "Very well. What would you like the password to be (do not use the # symbol): " CELERY_PWD
    fi


    read -p "
Great. This is all the input we need for a while. We will now complete the
installation process.

Press enter to proceed, or Ctrl+C to abort. " proceed
}


function check_deps {
    # this function checks for various dependencies that the script assumes are
    # installed for its own functionality.
    deps=(aptitude antiword checkinstall daemon g++ gcc git-core ipython libmysqlclient-dev libmysql++-dev libwpd-tools logrotate make mercurial mysql-client mysql-server poppler-utils pylint python python-beautifulsoup python-chardet python-dateutil python-docutils python-mysqldb python-pip python-pyparsing python-setuptools rabbitmq-server subversion tar wget)
    echo -e "\n########################"
    echo "Checking dependencies..."
    echo "########################"
    read -p "Do you need to check and install dependencies? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    for dep in ${deps[@]}
    do
        echo -n "Checking for $dep..."
        if dpkg -l $dep 2>/dev/null | grep -q ^.i
        then
            echo "found."
        else
            echo "MISSING."
            if [ $dep == "aptitude" ]
            then
                echo "Aborting. Fatal error. Please install aptitude and try again."
                exit 3
            else
                missingDeps=( ${missingDeps[@]-} $dep )
            fi
        fi
    done

    if [ $missingDeps ]
    then
        echo -e "\nThe following dependencies are missing: "
        echo "  ${missingDeps[@]-}"
        read -p "Install? (y/n): " proceed
        if [ $proceed == "y" ]
        then
            # after checking everything, install missing things, with user permission.
            aptitude install -P ${missingDeps[@]-}
            if [ $? != "0" ]
            then
                echo "Unable to properly install dependencies. Exiting."
                exit 3
            fi
        else
            echo "Unable to properly install dependencies. Aborting."
            exit 3
        fi
    fi
    echo -e "\nAll dependencies installed successfully."
}


function install_django {
    # this process simply installs django. Configuration is done later.
    echo -e "\n####################"
    echo "Installing django..."
    echo "####################"
    read -p "Would you like to download and configure version 1.2.x of django? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    if [ ! -d $DJANGO_INSTALL_DIR ]
    then
        read -p "Directory '$DJANGO_INSTALL_DIR' doesn't exist. Create it? (y/n): " proceed
        if [ $proceed == "n" ]
        then
            echo "Bad juju. Aborting."
            exit 5
        else
            mkdir -p $DJANGO_INSTALL_DIR
        fi
    fi

    # get django!
    echo "Downloading django with svn..."
    cd $DJANGO_INSTALL_DIR
    svn co http://code.djangoproject.com/svn/django/branches/releases/1.2.X .


    # link django with python
    if [ ! -d $PYTHON_SITES_PACKAGES_DIR ]
    then
        echo "PYTHON_SITES_PACKAGES_DIR does not exist. Aborting."
    else
        echo -n "Linking python with django..."
        sleep 0.5
        ln -s `pwd`/django $PYTHON_SITES_PACKAGES_DIR/django
        echo "Done."
    fi
    echo -e "\nDjango installed successfully."
}


function install_court_listener {
    # this is probably the most tricky part of the operation. We get the courtlistener
    # code, place it in the correct location, and then configure the heck out of
    # it.
    echo -e "\n########################"
    echo "Downloading and configuring CourtListener itself..."
    echo "########################"
    read -p "Would you like to download and configure CourtListener? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    if [ ! -d $CL_INSTALL_DIR ]
    then
        read -p "Directory '$CL_INSTALL_DIR' doesn't exist. Create it? (y/n): " proceed
        if [ $proceed == "n" ]
        then
            echo "Bad juju. Aborting."
            exit 5
        else
            mkdir -p $CL_INSTALL_DIR
        fi
    fi
    cd $CL_INSTALL_DIR
    echo "Downloading CourtListener with mercurial..."
    hg clone https://bitbucket.org/mlissner/search-and-awareness-platform-courtlistener court-listener

    # begin the harder thing: configuring it correctly...
    # We need a link between the 20-private.conf adminMedia location and the
    # location of the django installation. Else, admin templates won't work.
    ln -s $DJANGO_INSTALL_DIR/django/contrib/admin/media court-listener/alert/assets/media/adminMedia

    # we link up the init scripts
    echo "Installing init scripts in /etc/init.d/scraper"
    ln -s $CL_INSTALL_DIR/court-listener/init-scripts/scraper /etc/init.d/scraper
    update-rc.d scraper defaults

    # we create the logging file and set up logrotate scripts
    mkdir -p "/var/log/scraper"
    touch /var/log/scraper/daemon_log.out
    ln -s $CL_INSTALL_DIR/court-listener/log-scripts/scraper /etc/logrotate.d/scraper

    # this generates a nice random number, as it is done by django-admin.py
    SECRET_KEY=`python -c 'from random import choice; print "".join([choice("abcdefghijklmnopqrstuvwxyz0123456789") for i in range(50)]);'`

    # this is the MEDIA_ROOT
    MEDIA_ROOT="$CL_INSTALL_DIR/court-listener/alert/assets/media/"
    TEMPLATE_DIRS="$CL_INSTALL_DIR/court-listener/alert/assets/templates/"
    DUMP_DIR="$CL_INSTALL_DIR/court-listener/alert/assets/media/dumps/"

    # convert true and false (bash) to True and False (Python)
    if $DEVELOPMENT
    then
        DEVELOPMENT="True"
    else
        DEVELOPMENT="False"
    fi

    # all settings should be in place. Now we make the file...
    echo -e "\nGenerating the installation config, 20-private.conf..."
cat <<EOF > $CL_INSTALL_DIR/court-listener/alert/settings/20-private.conf
ADMINS = (
    ('$CONFIG_NAME', '$CONFIG_EMAIL'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'mysql', # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': '$MYSQL_DB_NAME',                      # Or path to database file if using sqlite3.
        'USER': '$MYSQL_USERNAME',                      # Not used with sqlite3.
        'PASSWORD': '$MYSQL_PWD',                  # Not used with sqlite3.
        'HOST': '',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    }
}

# Make this unique, and don't share it with anybody.
SECRET_KEY = '$SECRET_KEY'

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/media/adminMedia/'

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'America/Los_Angeles'
MEDIA_ROOT = '$MEDIA_ROOT'
DUMP_DIR = '$DUMP_DIR'

DEBUG = True

TEMPLATE_DIRS = (
    # put strings here, like "home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, evn on Windows.
    # Don't forget to use absolute paths, not relative paths.
    '$TEMPLATE_DIRS',
)


TEMPLATE_DEBUG = DEBUG

DEVELOPMENT = $DEVELOPMENT

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# this setting helps with settings elsewhere...include a trailing slash!
INSTALL_ROOT = '$CL_INSTALL_DIR/court-listener/'

INTERNAL_IPS = ('127.0.0.1',)
DEBUG_TOOLBAR_CONFIG = {'INTERCEPT_REDIRECTS': False}

# Celery settings
BROKER_USER = 'celery'
BROKER_PASSWORD = '$CELERY_PWD'

INSTALLED_APPS.extend([
EOF

    if [ $INSTALL_DEBUG_TOOLBAR == 'y' ]
    then
        echo "    'debug_toolbar'," >> $CL_INSTALL_DIR/court-listener/alert/settings/20-private.conf
    fi
    if [ $INSTALL_DJANGO_EXTENSIONS == 'y' ]
    then
        echo "    'django_extensions'," >> $CL_INSTALL_DIR/court-listener/alert/settings/20-private.conf
    fi
    echo "])" >> $CL_INSTALL_DIR/court-listener/alert/settings/20-private.conf #this closes off the INSTALLED_APPS var.

    echo -e 'Done\n\nCourtListener installed and configured successfully.'

    # TODO: Add some useful aliases here. Research the best way to do this.

}


function configure_mysql {
    echo -e "\n####################"
    echo "Configuring MySQL..."
    echo "####################"
    read -p "Would you like to configure MySQL? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    # create and configure the db.
    # first, we make a SQL script, then we execute it, then we delete it.
    cat <<EOF > install.sql
CREATE DATABASE $MYSQL_DB_NAME CHARACTER SET utf8;
GRANT ALL ON $MYSQL_DB_NAME.* to $MYSQL_USERNAME WITH GRANT OPTION;
SET PASSWORD FOR $MYSQL_USERNAME = password('$MYSQL_PWD');
FlUSH PRIVILEGES;
EOF
    echo -e "\nWe are about to create the database $MYSQL_DB_NAME, with username
$MYSQL_USERNAME and password $MYSQL_PWD."
    read -p "Press enter to continue, or Ctrl+C to abort." proceed
    echo "Please enter your root MySQL password."
    mysql -u'root' -p < install.sql
    if [ $? == "0" ]
    then
        rm install.sql
        echo -e '\nMySQL configured successfully.'
    else
        echo -e '\nError configuring MySQL. Aborting.'
        exit 7
    fi
}


#############################################################################
# This function lives on only because eventually we'll want it. For now, it #
# does nothing. I have often wanted to delete it...yet somehow it survives. #
#############################################################################
function install_ffmpeg {
    echo -e "\n####################"
    echo "Installing FFmpeg..."
    echo "####################"
    echo -e "\nFFmpeg is used by CourtListener to transcode audio files, but
unfortunately, the version that ships in most Debian derivatives is a tad old, and
installing from source is necessary.\n"
    read -p "Install FFmpeg from source now? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nYou can install this at a later date with the --ffmpeg flag.'
        return 0
    fi

    read -p "The default location for FFmpeg is /usr/local/ffmpeg. Is this OK? (y/n): " proceed
    if [ $proceed == 'n' ]
    then
        read -p "Where shall we install FFmpeg (starting at /, no trailing slash): " FFMPEG_INSTALL_DIR
    else
        FFMPEG_INSTALL_DIR='/usr/local/ffmpeg'
    fi

    if [ ! -d $FFMPEG_INSTALL_DIR ]
    then
        read -p "Directory '$FFMPEG_INSTALL_DIR' doesn't exist. Create it? (y/n): " proceed
        if [ $proceed == "n" ]
        then
            echo "Bad juju. Aborting."
            exit 5
        else
            mkdir -p $FFMPEG_INSTALL_DIR
        fi
    fi

    cd $FFMPEG_INSTALL_DIR

    echo "Removing old versions..."
    aptitude remove -P ffmpeg libmp3lame-dev libx264-dev

    echo "Installing dependencies..."
    aptitude install -P nasm

    # Installs lame
    echo "Downloading lame from source..."
    wget 'http://softlayer.dl.sourceforge.net/project/lame/lame/3.98.4/lame-3.98.4.tar.gz'
    tar xzvf lame-3.98.4.tar.gz
    mv lame-3.98.4 lame
    cd lame
    ./configure --enable-nasm --disable-shared
    make
    make install

    # Installs FFmpeg from source
    cd $FFMPEG_INSTALL_DIR
    svn checkout svn://svn.ffmpeg.org/ffmpeg/trunk ffmpeg
    cd ffmpeg
    ./configure --enable-gpl --enable-version3 --enable-nonfree --enable-postproc --enable-libopencore-amrnb --enable-libopencore-amrwb --enable-libtheora --enable-libvorbis --enable-libmp3lame --enable-libxvid --enable-x11grab
    make
    checkinstall --pkgname=ffmpeg --pkgversion "4:SVN-r`LANG=C svn info | grep Revision | awk '{ print $NF }'`" --backup=no --default --deldoc=yes
    hash ffmpeg ffplay

    echo -e '\nFFmpeg installed successfully.'
}


function install_solr {
    echo -e "\n####################"
    echo "Installing Solr..."
    echo "####################"
    read -p "Would you like to install Solr? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    # install pysolr
    echo "Installing pysolr..."
    easy_install pysolr
    
    cd /usr/local
    echo "Downloading Solr 4.0 development snapshot from 2011-11-04..."
    wget https://builds.apache.org/job/Solr-trunk/lastBuild/artifact/artifacts/apache-solr-4.0-2011-11-04_09-29-42.tgz
    
    echo "Unpacking Solr to /usr/local/solr..."
    tar -x -f apache-solr-4.0-2011-11-04_09-29-42.tgz
    mv apache-solr-4.0-2011-11-04_09-29-42 solr 
    rm apache-solr-4.0-2011-11-04_09-29-42.tgz 
    
    # make a directory where logs will be created and set up the logger
    ln -s $CL_INSTALL_DIR/court-listener/log-scripts/solr /etc/logrotate.d/solr
    
    # Enable Solr at startup
    ln -s $CL_INSTALL_DIR/court-listener/init-scripts/solr /etc/init.d/solr
    update-rc.d solr defaults
    
    # next we configure the thing...this is going to be ugly.
    TODO, if config can't go into Hg.
    
    # and hopefully that worked...
    echo -e "\nSolr installed successfully."
}


function install_haystack {
    echo -e "\n###########################"
    echo "Installing Haystack..."
    echo "###########################"
    read -p "Would you like to install Haystack? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    # we install Haystack
    easy_install django-haystack==1.2.5
    
    echo -e '\nHaystack installed successfully.'
}


function install_django_celery {
    echo -e '\n##################################'
    echo 'Installing django-celery and Celery...'
    echo '##################################
'
    read -p "Install django-celery and Celery on this computer? (y/n): " proceed
    if [ $proceed == "y" ]
    then
        # we install them
        pip install django-celery

        # create a system user account
        echo "Adding celery to rabbitmq..."
        rabbitmqctl add_vhost "/celery"
        sudo rabbitmqctl add_user celery "$CELERY_PWD"
        sudo rabbitmqctl set_permissions -p "/celery" "celery" ".*" ".*" ".*"

        # Make an unprivileged, non-password-enabled user and group to run celery
        useradd celery
        
        # make a spot for the logs and the pid files
        mkdir /var/log/celery
        mkdir /var/run/celery
        chown celery:celery /var/log/celery
        chown celery:celery /var/run/celery
        
        # set up the logger
        ln -s $CL_INSTALL_DIR/court-listener/log-scripts/celery /etc/logrotate.d/celery
        
        echo "Installing init scripts in /etc/init.d/celeryd"
        ln -s $CL_INSTALL_DIR/court-listener/init-scripts/celeryd /etc/init.d/celeryd
        update-rc.d celeryd defaults
              
        echo -e '\nDjango-celery and Celery installed successfully.'
    else
        echo -e '\nGreat. Moving on.'
        return 0
    fi
}


function install_debug_toolbar {
    if [ $INSTALL_DEBUG_TOOLBAR == 'y' ]
    then
        echo -e '\n##################################'
        echo 'Installing django debug toolbar...'
        echo '##################################
'
        read -p "Install django debug toolbar on this computer? (y/n): " proceed
        if [ $proceed == "y" ]
        then
            # we install it
            pip install django-debug-toolbar
            echo -e '\nDjango debug toolbar installed successfully.'
        else
            echo -e '\nGreat. Moving on.'
            return 0
        fi
    fi
}


function install_django_extensions {
    if [ $INSTALL_DJANGO_EXTENSIONS == 'y' ]
    then
        echo -e '\n###############################'
        echo 'Installing django-extensions...'
        echo '###############################
'
        read -p "Install django-extensions on this computer? (y/n): " proceed
        if [ $proceed == "n" ]
        then
            echo -e '\nGreat. Moving on.'
            return 0
        fi

        # install it
        cd $DJANGO_INSTALL_DIR
        git clone git://github.com/django-extensions/django-extensions.git django-extensions
        cd django-extensions
        python setup.py install

        echo -e '\ndjango-extensions installed successfully.'
    fi
}


function install_south {
    echo -e '\n###################'
    echo 'Installing South...'
    echo '###################'

    read -p "Install South on this computer? (y/n): " proceed
    if [ $proceed == 'n' ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    # install the mo'
    cd $DJANGO_INSTALL_DIR
    hg clone http://bitbucket.org/andrewgodwin/south/ South
    cd South
    python setup.py develop

    echo -e '\nSouth installed successfully.'
}


function import_data {
    # TODO: replace with an API call (once the API exists)
    echo -e "\n############################"
    echo "Importing data into MySQL..."
    echo "############################"
    read -p "Would you like to set up the DB with information about the courts? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    # import data using the manage.py function. Data can be regenerated with:
    # python manage.py dumpdata alerts.Court
    cd $CL_INSTALL_DIR/court-listener/alert
    cat <<EOF > /tmp/courts.json
[{"pk": "ca1", "model": "search.court", "fields": {"URL": "http://www.ca1.uscourts.gov", "startDate": "1891-03-03", "shortName": "1st Cir.", "endDate": null}}, {"pk": "ca10", "model": "search.court", "fields": {"URL": "http://www.ca10.uscourts.gov", "startDate": "1929-02-28", "shortName": "10th Cir.", "endDate": null}}, {"pk": "ca11", "model": "search.court", "fields": {"URL": "http://www.ca11.uscourts.gov", "startDate": "1980-10-14", "shortName": "11th Cir.", "endDate": null}}, {"pk": "ca2", "model": "search.court", "fields": {"URL": "http://www.ca2.uscourts.gov", "startDate": "1891-03-03", "shortName": "2d Cir.", "endDate": null}}, {"pk": "ca3", "model": "search.court", "fields": {"URL": "http://www.ca3.uscourts.gov", "startDate": "1891-03-03", "shortName": "3rd Cir.", "endDate": null}}, {"pk": "ca4", "model": "search.court", "fields": {"URL": "http://www.ca4.uscourts.gov", "startDate": "1891-03-03", "shortName": "4th Cir.", "endDate": null}}, {"pk": "ca5", "model": "search.court", "fields": {"URL": "http://www.ca5.uscourts.gov", "startDate": "1891-03-03", "shortName": "5th Cir.", "endDate": null}}, {"pk": "ca6", "model": "search.court", "fields": {"URL": "http://www.ca6.uscourts.gov", "startDate": "1891-03-03", "shortName": "6th Cir.", "endDate": null}}, {"pk": "ca7", "model": "search.court", "fields": {"URL": "http://www.ca7.uscourts.gov", "startDate": "1891-03-03", "shortName": "7th Cir.", "endDate": null}}, {"pk": "ca8", "model": "search.court", "fields": {"URL": "http://www.ca8.uscourts.gov", "startDate": "1891-03-03", "shortName": "8th Cir.", "endDate": null}}, {"pk": "ca9", "model": "search.court", "fields": {"URL": "http://www.ca9.uscourts.gov", "startDate": "1891-03-03", "shortName": "9th Cir.", "endDate": null}}, {"pk": "cadc", "model": "search.court", "fields": {"URL": "http://www.cadc.uscourts.gov", "startDate": "1893-02-09", "shortName": "D.C. Cir.", "endDate": null}}, {"pk": "cafc", "model": "search.court", "fields": {"URL": "http://www.cafc.uscourts.gov", "startDate": "1982-04-02", "shortName": "Fed. Cir.", "endDate": null}}, {"pk": "cc", "model": "search.court", "fields": {"URL": "http://www.fjc.gov/history/home.nsf/page/courts_special_coc.html", "startDate": "1855-02-24", "shortName": "Ct. Cl.", "endDate": "1982-04-02"}}, {"pk": "ccpa", "model": "search.court", "fields": {"URL": "http://www.cafc.uscourts.gov/", "startDate": "1909-08-05", "shortName": "C.C.P.A.", "endDate": "1982-04-02"}}, {"pk": "uscfc", "model": "search.court", "fields": {"URL": "http://www.uscfc.uscourts.gov/", "startDate": "1982-04-02", "shortName": "Fed. Cl.", "endDate": null}}, {"pk": "cit", "model": "search.court", "fields": {"URL": "http://www.cit.uscourts.gov", "startDate": "1980-10-10", "shortName": "Ct. Int'l Trade", "endDate": null}}, {"pk": "com", "model": "search.court", "fields": {"URL": "http://www.fjc.gov/history/home.nsf/page/courts_special_com.html", "startDate": "1910-06-18", "shortName": "Comm. Ct.", "endDate": "1913-12-31"}}, {"pk": "cusc", "model": "search.court", "fields": {"URL": "http://www.fjc.gov/history/home.nsf/page/courts_special_cc.html", "startDate": "1890-06-10", "shortName": "Cust. Ct.", "endDate": "1980-10-10"}}, {"pk": "eca", "model": "search.court", "fields": {"URL": "https://secure.wikimedia.org/wikipedia/en/wiki/Emergency_Court_of_Appeals", "startDate": "1942-01-30", "shortName": "Emer. Ct. App.", "endDate": "1962-04-18"}}, {"pk": "scotus", "model": "search.court", "fields": {"URL": "http://supremecourt.gov", "startDate": "1789-09-24", "shortName": "SCOTUS", "endDate": null}}, {"pk": "tecoa", "model": "search.court", "fields": {"URL": "http://www.fjc.gov/history/home.nsf/page/courts_special_tecoa.html", "startDate": "1971-12-22", "shortName": "Temp. Emer. Ct. App.", "endDate": "1993-03-29"}}]
EOF
    python manage.py syncdb
    python manage.py migrate
    python manage.py loaddata /tmp/courts.json
    rm /tmp/courts.json

    echo -e '\nInformation loaded into the database successfully.'
}


function finalize {
    echo -e '\n##############################'
    echo 'Finalizing the installation...'
    echo '##############################'
    read -p "Would you like to finalize the installation? (y/n): " proceed
    if [ $proceed == "n" ]
    then
        echo -e '\nGreat. Moving on.'
        return 0
    fi

    echo -e '\nSyncing the django data model...'
    cd $CL_INSTALL_DIR/court-listener/alert
    python manage.py syncdb
    python manage.py migrate

    echo -e '\nInstallation finalized successfully.'
}


function main {
    # run the program!
    get_user_input
    check_deps
    installDjango
    installCourtListener
    configure_mysql
    installSolr
    installHaystack
    installDjangoCelery
    installDebugToolbar
    installDjangoExtensions
    installSouth
    importData
    finalize

    echo -e "\n\n#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#"
    echo '  CourtListener was completely installed correctly!'
    echo "#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#"
    echo "You may test this installation by going to $CL_INSTALL_DIR/court-listener/alert
and running the command:
    $ python manage.py runserver
If that works, you should be able to see the CourtListener website in your browser
at http://localhost:8000.


"
    read -p "Press enter to exit the install script, and begin hacking. Whew."
    exit 0
}


#initiation sequence
if [ $# -eq 0 -o $# -gt 1 ]
then
    # We need to give them help using the program.
    echo "install.sh:  Invalid number of arguments."
    echo "Usage: install.sh --help | --install"
    exit 2
elif [[ $EUID -ne 0 ]];
then
    echo "install.sh: This script must be run as root" 1>&2
    exit 2
else
    case $1 in
        --help) print_help;;
        --install) main;;
        --checkdeps) check_deps;;
        --mysql) get_user_input; configure_mysql;;
        --ffmpeg) get_user_input; install_ffmpeg;;
        --solr) get_user_input; install_solr;;
        --django) get_user_input; install_django;;
        --courtlistener) get_user_input; install_court_listener;;
        --importdata) get_user_input; configure_mysql; import_data;;
        --debugtoolbar) get_user_input; install_debug_toolbar;;
        --djangocelery) get_user_input; install_django_celery;;
        --djangosolr) get_user_input; install_haystack;;
        --djangoExtensions) get_user_input; install_django_extensions;;
        --south) get_user_input; install_south; finalize;;
        --finalize) get_user_input; finalize;;
        *) echo "install.sh: Invalid argument. Try the --help argument."
           exit 2;
    esac
fi

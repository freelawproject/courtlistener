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
#!/bin/bash

# This script is designed to install the CourtListener project on a Linux 
# machine. It was written for Ubuntu Lucid Linux - v. 10.04, but should work on
# most debian derivatives.
#
# This script should also serve as the documentation for the installation 
# process.

# This script does the following:
# - check for its own dependencies (such as aptitude, hg, svn, etc)
# - get various input from the user.
# - install django from source
# - install CourtListener from source
# - install & configure Sphinx
# - install django-sphinx
# - configure mysql & courtlistener
# - sync the django configuration
# - exit


function printHelp {
cat <<EOF
NAME
    install.sh

SYNOPSIS
    install.sh --help | --install

OPTIONS
    This program will install the courtlistener software on your computer. It 
    makes a number of assumptions, but does its best. Patches and contributions
    are welcome.

    --help     Print this help file

    --install  Install the courtlistener software

EXIT STATUS
    0   The installation was successful.
    >0  An error occured, as follows:
        1   Unknown error
        2   Invalid usage
        3   Missing critical dependency
        4   Errors installing django from source
        5   Error getting user input

AUTHOR AND COPYRIGHT
    This script was authored by Michael Lissner and is released under the same 
    permissive license as the remainder of the courtlistener program.

EOF
}


function getUserInput {
cat<<EOF
Welcome to the install script. This script will install the courtlistener 
system on your Debian-based Linux computer. We will begin by gathering several 
pieces of input from you, and then we will install django, courtlistener, 
sphinx, django-sphinx, MySQL, and all their dependencies.
EOF
    read -p "Shall we continue? " proceed
    if [ $proceed != 'y' ]
    then
        exit 2
    else
        sleep 0.5
        echo -e "Great. Off we go then.\n"
    fi
    
    # this function sets some variables that will be used throughout the program
    read -p "The default location for your django installation is /opt. Is this OK? (Y/n): " proceed
    if [ $proceed == "n" ]
    then
        read -p "Where shall we install django (starting at /)?: " DJANGO_INSTALL_DIR
    else
        DJANGO_INSTALL_DIR = '/opt'
    fi
    
    # set up the PYTHON_SITES_PACKAGES_DIR
    PYTHON_SITES_PACKAGES_DIR=`python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"`
    read -p "The default location for your CourtListener installation is /var/www. Is this OK? (Y/n): " proceed
    if [ $proceed == 'n' ]
    then
        read -p "Where shall we install CourtListener (starting at /)?: " CL_INSTALL_DIR
    else
        CL_INSTALL_DIR = '/var/www'
    fi
    
    # set up the private settings file
    echo "We are going to set up two settings files. One with private data, "
    echo "and one with public data. For the private data, we will need to gather"
    echo "some information. This file should NEVER be checked into revision control!"
    read -p "What name would you like used as the admin name for the site (e.g. Michael Lissner): " CONFIG_NAME
    read -p "What email address should be used for the admin of the site (e.g. mike@courtlistener.com): " CONFIG_EMAIL
    echo "Great. These are stored in a tuple in the 20-private.conf file. You "
    echo "can add more people manually, if you like. Managers, will be set equal"
    echo "to the admins. This too can be changed."
    echo -e "\nDebug is set to True."
    echo "CACHE_BACKEND is not set (which is fine for a dev machine)."
    echo "TEMPLATE_DEBUG is set to DEBUG."
    echo "DEVELOPMENT is set to True (which helps with the runserver command, see urls.py for details)."
    echo  "Your time zone is set to America/Los Angeles"
    
    
    # set up the MySQL configs
    read -p "We will be setting up a MySQL DB. What would you like its name to be (suggest: courtListener): " MYSQL_DB_NAME
    read -p "And we will be giving it a username. What would you like that to be: " MYSQL_USERNAME
    read -p "And its password? You likely won't need it very often. Make it long and crazy: " MYSQL_PWD
}


function checkDeps {
    # this function checks for various dependencies that the script assumes are 
    # installed for its own functionality.
    deps=(aptitude hg python python-beautifulsoup python-docutils python-mysqldb popler-utils mysql-client mysql-server svn)
    echo "########################"
    echo "Checking dependencies..."
    echo "########################"
    for dep in ${deps[@]}
    do
        echo -n "Checking for $dep..."
        sleep 0.5
        if type -P $dep &> /dev/null
        then
            echo "found."
        else
            echo "MISSING."
            if [ $dep == "aptitude" ]
            then
                echo "Aborting. Fatal error. Please install aptitude and try again."
                exit 3
            else
                # if the program is missing, add it to a new list, and move on.
                # special cases...ug.
                if [ $dep == "hg" ]
                then
                    missingDeps=( ${missingDeps[@]-} mercurial )
                elif [ $dep == "subversion" ]
                then
                    missingDeps=( ${missingDeps[@]-} subversion )
                else
                    missingDeps=( ${missingDeps[@]-} $dep )
                fi
            fi
        fi
    done
    
    if [ $missingDeps ]
    then
        echo -e "\nThe following dependencies are missing:"
        echo "  ${missingDeps[@]-}"
        read -p "install? " proceed
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


function installDjango {
    # this process simply installs django. Configuration is done later.
    echo "####################"
    echo "Installing django..."
    echo "####################"
    if [ ! -d $DJANGO_INSTALL_DIR ]
    then
        read -p "Directory doesn't exist. Create it? (Y/n): " proceed
        if [ $proceed == "n" ]
        then
            echo "Bad juju. Aborting."
            exit 5
        else
            mkdir $DJANGO_INSTALL_DIR
        fi
    fi

    # get django!
    echo "Downloading django with svn..."
    cd $DJANGO_INSTALL_DIR
    svn co http://code.djangoproject.com/svn/django/trunk/ django-trunk
    
    # link django with python
    if [ ! -d $PYTHON_SITES_PACKAGES_DIR ]
    then
        echo "PYTHON_SITES_PACKAGES_DIR does not exist. Aborting."
    else
        echo -n "Linking python with django..."
        sleep 0.5
        ln -s `pwd`/django-trunk/django $PYTHON_SITES_PACKAGES_DIR/django
        echo "Done."
    fi
    echo -e "\nDjango installed successfully."
}


function installCourtListener {
    # this is probably the most tricky part of the operation. We get the courtlistener
    # code, place it in the correct location, and then configure the heck out of
    # it.
    echo "########################"
    echo "Downloading and configuring CourtListener itself"
    echo "########################"
    cd $CL_INSTALL_DIR
    echo "Downloading CourtListener with mercurial..."
    hg clone https://mlissner@bitbucket.org/mlissner/legal-current-awareness court-listener

    # begin the harder thing: configuring it correctly...    
    # We need a link between the 20-private.conf adminMedia location and the 
    # location of the django installation. Else, admin templates won't work.
    ln -s $DJANGO_INSTALL_DIR/django-trunk/django/contrib/admin/media court-listener/alert/assets/media/adminMedia
        
    # this generates a nice random number, as it is done by django-admin.py
    SECRET_KEY = `python -c 'from random import choice; print "".join([choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]);'`
    # this is the MEDIA_ROOT
    MEDIA_ROOT = "$CL_INSTALL_DIR/court-listener/alert/assets/media/"
    TEMPLATE_DIRS = "$CL_INSTALL_DIR/court-listener/alert/assets/templates/"
    
    # all settings should be in place. Now we make the file...
    touch $CL_INSTALL_DIR/court-listener/alert/settings/20-private.conf
cat <<EOF > $CL_INSTALL_DIR/court-listener/alert/settings/20-private.conf
ADMINS = (
    ('$CONFIG_NAME', '$CONFIG_EMAIL'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'mysql', # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': '$MYSQL_DB_NAME',                      # Or path to database file if using sqlite3.
        'USER': 'MYSQL_USERNAME',                      # Not used with sqlite3.
        'PASSWORD': 'MYSQL_PWD',                  # Not used with sqlite3.
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

DEBUG = True

TEMPLATE_DIRS = (
    # put strings here, like "home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, evn on Windows.
    # Don't forget to use absolute paths, not relative paths.
    '$TEMPLATE_DIRS',
)


TEMPLATE_DEBUG = DEBUG

DEVELOPMENT = True

#EMAIL_BACKEND is set to default, so nothing listed here.

<<EOF
    echo -e '\nCourtListener installed and configured successfully.'
}


function configureMySQL {
    
    cd $CL_INSTALL_DIR/court-listener
    python manage.py syncdb
}


function installSphinx {
    echo "####################"
    echo "Installing Sphinx..."
    echo "####################"
    cd CL_INSTALL_DIR/court-listener/Sphinx

    
    
    
}

function installDebugToolbar {
    read -p "Is the django debug toolbar installed on this computer? (y/N): " installed
    if [ $installed == "n" ]
    then
        echo '##################################'
        echo 'Installing django debug toolbar...'
        echo '##################################'
        # we install it
        XXXXXXXXXXXXXXXX
    fi
    echo -e '\nDjango debug toolbar installed successfully.'
}

function main {
    # run the program!
    getUserInput
    checkDeps
    installDjango
    installCourtListener
    configureMySQL
    installSphinx
    installDebugToolbar
    echo -e '\nCourtListener was completely installed correctly.'
    read "Press any key to continue. "
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
        --help) printHelp;;
        --install) main;;
        *) echo "autocompleteDestroyer.sh: Invalid argument. Try the --help argument."
           exit 2;
    esac
fi

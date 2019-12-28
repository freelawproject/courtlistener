Eventually, this readme is meant to be fleshed out with lots of details about
how to do migrations without any particular issues, but for the moment it's 
just a pointer to a bug that highlights the most grievous types of problems:

https://github.com/freelawproject/courtlistener/issues/1106

Please, before you do an automated migration, check the SQL that it will run by
using `sqlmigrate`, and be sure that the SQL doesn't run afoul of the major
problems listed in that bug report.

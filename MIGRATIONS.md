Eventually, this readme is meant to be fleshed out with lots of details about
how to do migrations without any particular issues, but for the moment it's 
just a pointer to bugs that highlight the most grievous types of problems:

https://github.com/freelawproject/courtlistener/issues/1106
https://github.com/freelawproject/courtlistener/issues/1109

Please, before you do an automated migration, check the SQL that it will run by
using `sqlmigrate`, and be sure that the SQL doesn't run afoul of the major
problems listed in those bug report or below.

# Known Problems

## New columns With DEFAULT values in Postgresql < v11 

The main problem listed there is creating new columns with DEFAULT values, 
which the standard migrations *do*. Those can be fine in regular environments,
but in ours, where we have huge tables, it can be a big deal. In Postgresql 11
this is finally fixed.

# Making data changes in same transaction as schema changes

The second problem you can run into is that you cannot make data changes in the 
same transaction as schema changes. Doing so can raise an error like:

    ERROR:  cannot ALTER TABLE "search_opinion" because it has pending trigger events

This post has some more information about this: https://stackoverflow.com/a/12838113/64911





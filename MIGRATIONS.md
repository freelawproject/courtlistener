Eventually, this readme is meant to be fleshed out with lots of details about
how to do migrations without any particular issues, but for the moment it's 
just a pointer to bugs that highlight the most grievous types of problems:

https://github.com/freelawproject/courtlistener/issues/1106

https://github.com/freelawproject/courtlistener/issues/1109

Please, before you do an automated migration, check the SQL that it will run by
using `sqlmigrate`, and be sure that the SQL doesn't run afoul of the major
problems listed in those bug report or below.

It's also worth reviewing these references, which point to problems that can 
occur on high-volume PostgreSQL instances like ours:

https://www.braintreepayments.com/blog/safe-operations-for-high-volume-postgresql/

https://github.com/ankane/strong_migrations

https://leopard.in.ua/2016/09/20/safe-and-unsafe-operations-postgresql


# Known Problems

## Migrations that do literally nothing

This isn't the worst crime, but sometimes Django can be pretty dumb. For 
example, if you convert a text field to be `blank=True`, that'll create a 
migration that sets `DEFAULT=''`, followed immediately by `DROP DEFAULT`. That
doesn't do anything except confuse things, so the first rule of good migrations
is: "Migrations should do something."


## New columns With DEFAULT values in Postgresql < v11 

The biggest issue we run into is that creating new columns with DEFAULT values, 
can be fine in regular environments, but cause a crisis in huge tables like the
ones we have. Django does this kind of migration by default when you create a 
new text column with `blank=True`. That's very bad and until we upgrade to 
Postgresql 11 we will have to contend with this issue.


## Adding an index to a column doesn't use CONCURRENTLY

Until [Django issue 21039][concur] is merged, Django creates indexes without using 
the `CONCURRENTLY` statement. This locks the table for the duration of the index 
creation. It takes more work, but this can be avoided by tweaking the Python and SQL
migration files [as described in this excellent blog post][concur-blog]. You can see
an example of this in CourtListener [too][ex].

[concur]: https://code.djangoproject.com/ticket/21039
[concur-blog]: https://realpython.com/create-django-index-without-downtime/
[ex]: https://github.com/freelawproject/courtlistener/pull/1132

## Making data changes in same transaction as schema changes

You cannot make data changes in the same transaction as schema changes. Doing 
so can raise an error like:

    ERROR:  cannot ALTER TABLE "search_opinion" because it has pending trigger events

This post has some more information about this: https://stackoverflow.com/a/12838113/64911





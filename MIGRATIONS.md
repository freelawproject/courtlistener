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
an example of this in CourtListener [too][ex]. Note that `CONCURRENTLY` can't 
be used in a transaction block.

[concur]: https://code.djangoproject.com/ticket/21039
[concur-blog]: https://realpython.com/create-django-index-without-downtime/
[ex]: https://github.com/freelawproject/courtlistener/pull/1132


## Making data changes in same transaction as schema changes

You cannot make data changes in the same transaction as schema changes. Doing 
so can raise an error like:

    ERROR:  cannot ALTER TABLE "search_opinion" because it has pending trigger events

This post has some more information about this: https://stackoverflow.com/a/12838113/64911



# Notes on schema changes

## Adding a column

If you add a column to the publisher that doesn't already exist on the 
subscriber you'll get a message at the subscriber that says something like:

    ERROR:  logical replication target relation "public.t" is missing some replicated columns
    
Or:

```
2018-12-09 05:59:45 UTC::@:[13373]:LOG: logical replication apply worker for subscription "replicasubscription" has started
2018-12-09 05:59:45 UTC::@:[13373]:ERROR: null value in column "recap_sequence_number" violates not-null constraint
2018-12-09 05:59:45 UTC::@:[13373]:DETAIL: Failing row contains (48064261, 2018-12-07 04:48:40.388377+00, 2018-12-07 04:48:40.388402+00, null, 576, , 4571214, null, null).
2018-12-09 05:59:45 UTC::@:[6342]:LOG: worker process: logical replication worker for subscription 18390 (PID 13373) exited with exit code 1
```

(See https://github.com/freelawproject/courtlistener/issues/919)
    
Both of these messages sort of make sense. In each you're trying to move data 
(or a null value) to the subscriber and the subscriber doesn't know what to do
with it. The fix, of course, is to have that column set up at the subscriber 
first, as hinted in the documentation:

> In many cases, intermittent errors can be avoided by applying additive schema 
> changes to the subscriber first. 


## Removing a column

If you remove a column at the subscriber first, you will receive tuples with 
fields you don't know how to handle. If you remove it at the publisher 
first, you'll have columns on the subscriber that don't know how to be 
populated. The general rule is to drop a column at the publisher first, then 
at the subscriber, once things have flushed. See:

https://github.com/freelawproject/courtlistener/issues/1164

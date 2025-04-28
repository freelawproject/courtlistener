# Short description of the sitemaps_infinite app

The sitemaps_infinite app is based on the SQL `cursor pagination` approach implemented in the `django-cursor-pagination` app.

## Idea

Cursor pagination allows to paginate huge database tables without using `OFFSET` SQL instruction, that makes the select very slow or even impossible when the number of records is very big. On the contrary, cursor pagination works in the constant time, no matter what page is being selected.

## Implementation

The app implements a custom `InfinitePaginatorSitemap` that uses `CustomCursorPaginator` that stores the pages information in the cache backend. That class should be a parent of the sitemap that is created for a certain document type with huge number of records.

The actual sitemap pages generation is implemented in the form of sequential pre-generation, because normal pagination (based on 'page number' parameters) is not possible for cursor pagination.

The pregenerated pages with added metadata are then saved with the same `cache_key` that is used for the regular sitemap pages, generated 'on the fly' by default 'sitemaps' app.

There is a separate route defined for the sitemaps_infinite pages to differentiate them from the normal ones.

The app also contains a celery task doing the same that `generate_sitemaps` command does.

### Details

The document type should have a unique key with the index, that is used for the cursor iteration. By default the primary key is used for that purpose.

The generation command sequentially takes sitemap sections and iterate all pages in each section until the files limit is hit, to decrease the impact on the database and cache.
The last section and cursor is saved in the `redis` DB and the next command invocation will continue the generation process.

This command should be called periodically to make sure the new pages are added or the existing ones are updated properly.

### Settings

The main settings are:
`cl/sitemaps_infinite/urls.py`:
  - `pregenerated_sitemaps` contains the list of infinite sitemaps classes that should use pregenerated approach, they are served via the `large-sitemap*` routes.

`.env`:
  - `SITEMAPS_FILES_PER_CALL` - The number of sitemap 'files' (pages) to cache per single sitemap generation call (10 by default)
  - `SITEMAPS_TASK_REPEAT_SEC` - call sitemap file generation every `SITEMAPS_TASK_REPEAT_SEC` seconds via celery, set 0 to disable task (default)

The domain of the sitemap urls is retrieved from the `django.contrib.sites` current site.

The `DocketSitemap` from `cl/opinion_page` app is currently implemented as an example.

You need to submit the new `/large-sitemap.xml` url to google.com in order to index all the large sitemaps, generated using this module.
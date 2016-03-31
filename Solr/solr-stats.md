### 2016-02-02
Ran an update against entire db on new server. Completed in 366 minutes with
almost exactly 3M docs.

### 2013-09-17
Re-index to add citation field. 905403 docs, 170 minutes.

### 2013-06-27
Re-index to add citation counts, judges and suitNature. 894,000 docs, about
2-3 hours.

### 2013-01-11
Initial index on new machine with 24 cores, SSD drives, etc. Index has 770,000
docs. Took 94 minutes, including optimizing the index  (135.5 docs/sec).
Created index was 19GB in size. Now officially on Solr 4.0 and postgres.

### 2012-03-08
Had to reindex after *accidental* deletion of index with 605188 documents.
Took 38981 seconds, including optimizing the index (15.5 docs/sec). The index
created was 14GB in size.

### 2012-01-28
After implementing Celery Tasksets, indexing 602039 documents took 32427 seconds,
including optimizing the index (18.6 docs/sec). The index created was 15GB in size.

### 2012-01-22
Prior to implementing Celery Tasksets, indexing 601290 documents took 19606
seconds (~5.5hrs). However, this method overwhelmed Rabbitmq. The index created
was 18GB in size.

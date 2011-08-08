To do:
 - Check that the citations are going to the right place in the DB.
 - Check that the scraper still works.

When deploying:
 - need to migrate data:
    - python manage.py migrate alertSystem
    - run clean-scripts/move-westcitations-to-correct-column61.py
 - dumps are updated. Need to delete old ones, and test that empty attributes
   don't cause the entire doc not to show up. Once tested, tackle the bug about
   bad various bad bits of data in the case names, thennotify mailing list
   and Malamud.
 - Add courts to the DB using the admin interface or manage.py loaddata
 - clean the supreme court cases using: python scotus_case_name_cleaner.py -v
 - Add the entire f2 from resource.org, and point script at it.
 - need to recreate sphinx indexes.
    - update the SQL lines and infix fields manually
    - reindex.
    - update any saved queries from caseNumber --> docketNumber
 - Update the advanced search flat page to mention @docketNumber and @westCite

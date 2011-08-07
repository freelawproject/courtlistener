To do:
 - Check that the citations are going to the right place in the DB.

When deploying:
 - need to migrate data:
    - python manage.py migrate alertSystem
    - run clean-scripts/move-westcitations-to-correct-column61.py
 - need to recreate sphinx indexes.
    - update the SQL lines and infix fields manually
    - reindex.
    - update any saved queries from caseNumber --> docketNumber
 - dumps are updated. Need to delete old ones, and test that empty attributes
   don't cause the entire doc not to show up. Once tested, notify mailing list
   and Malamud.
 - Add courts to the DB using the admin interface or manage.py loaddata
 - Add the entire f2 from resource.org, and point script at it.
 - Update the advanced search flat page to mention @docketNumber and @westCite

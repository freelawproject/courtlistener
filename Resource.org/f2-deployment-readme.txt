To do:
 - change the link on the case page to say Download Original > At Resource.org
 - add width/height attributes to images in profile pages
 - use nbsp; in citations
 - check out the outliars in the DB by date
 - recreate the stat_maker.py script
 - Update flatpage for the sitemap, and update the list of courts on the browse
   page and anywhere else



When deploying:
 - all dumps are updated with docket numbers rather than case numbers. Need to
   delete old ones, and test that empty attributes don't cause the entire doc
   not to show up. Once tested, tackle the bug about various bad bits of
   data in the case names, then notify mailing list and Malamud.
 - Run MySQL optimize command


Done:
 - Check that the scraper still works. --> Done.
 - need to migrate data:
    - python manage.py migrate alertSystem --> Done.
    - run python clean-scripts/move-westcitations-to-correct-column61.py --> Done.
 - Update the advanced search flat page to mention @docketNumber and @westCite --> Done.
 - Add courts to the DB using the admin interface or manage.py loaddata --> Done.
 - clean the supreme court cases using: python scotus_case_name_cleaner.py -v --> Done.
 - Add the entire f2 from resource.org, and point script at it. --> Done.
 - make a shortcut from browse --> opinions/all --> Done.
 - make sure that the scotus scraper is filing the case/docket numbers correctly. --> Done.
 - need to recreate sphinx indexes.
    - update the SQL lines and infix fields manually --> Done
    - reindex. --> Done.
    - update any saved queries from caseNumber --> docketNumber --> Done

To do:
 - check out the outliars in the DB by date
 - recreate the stat_maker.py script (see bug)
 - create queue for parser (or similar, see bug)
 - Check the dates/courts in Brian's list of citation-less docs, and see if we
   missed any docs.
 - Do F3
    -
 - Import resource.org/robots.txt (see bug 187)
 - Why don't I get logs from the scraper daemon emailed?
 - Add harmonize code and test case for "The United States"


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
 - use nbsp; in citations --> Done
 - sort out why docket numbers aren't appearing correctly --> Done
 - add width/height attributes to images in profile pages --> Done
 - Update flatpage for the sitemap, and update the list of courts on the browse
   page and anywhere else
 - Remove border on error "Woah" page.
 - Emails:
    - Remove the download original link from emails. It's just not needed --> Done.
    - Make the Your Alert -- blah -- has x results line stand out more in txt emails --> Done.
 - valid fields error needs to be updated --> Done.
 - fix resource.org links (see bug) --> Done.
    - then: change the link on the case page to say Download Original > At Resource.org --> Done.
    - then: fix dumps --> Done.
        - then: notify mailing list and Malamud. --> Done.
 - announce the changes on the "blog"
 - remove all colborders, and replace with append-1
 - Change sitemap so it says original versions rather than PDFs, since we aren't
   exclusively dealing with PDFs
 - Remove resource.org links.
 - Figure out why result links are wrong.
 - create a nbsp filter
 - Apply <span class="alt"> to all 'v.' in document titles
 - fix @casename "unpublished disposition" cases (bug 182)
 - Investigate adding document back to the admin site for Brian
 - Fix display of  information on Resource.org HTML display (CSS)

**Proposed Change: Add a RECAP search option about representation.**

*This proposal stems from freelawproject/courtlistener issue #[806](https://github.com/freelawproject/courtlistener/issues/806).*

**CONTENTS**
- Problem statement
- Proposed solution by component
  - User Interface
  - Django code for analyzing and storing docket data
  - Solr
  - Already-stored docket data
  - Documentation
- Test cases

# Problem statement

PACER and RECAP search users do not currently have an option to search for dockets where at least one petitioner had representation. Searchers like to examine those dockets because they generally have higher quality complaints, motions, briefs, citations, and prose. Because that option is not available, searchers have to use other means that cost time and money to differentiate such cases from those where every petitioner is pro se.

# Proposed solution 

Enable a RECAP search option to exclude cases from the results where every petitioner was pro se.

Enabling the option requires changes in (1) the user interface, (2) the server-side Django code that analyzes and stores docket data, (3) the Solr search configuration, (4) the already-stored docket data, and (5) documentation.

Neither the RECAP browser extension nor Juriscraper will need to be changed.

## Proposed solution: User Interface

On the CourtListener.com [RECAP search page](https://www.courtlistener.com/recap/), **add** a checkbox to the search options.  The checkbox's label will be: "Exclude *pro se* petitioner cases".

Also, **add** a pop-up help tip through a question-mark icon with this text:
"If this box is checked, then cases where every petitioner is pro se will be excluded from the search results.  Parties treated as petitioners include plaintiffs, appellants, applicants, complainants, claimants, and relators. If a party's name does not match the corresponding attorney's name or no attorney name is provided, then the party is assumed to be pro se."

## Proposed solution:  Django code for analyzing and storing docket data

**Modify** the existing Django code that is for analyzing and storing docket data.  Start with the code that contains a representation of the data model.  **Add** boolean attributes that will be used to identify:
- For each docket party, whether each party is a petitioner or not.  E.g. `petitioner`.
- For each docket party, whether each party is pro se or not.  (E.g. `pro_se`.)
- For each docket, whether every petitioner is represented or not.  (E.g. `all_petitioners_pro_se`.)

The Django code will, in effect, change the data model and storage just like the following SQL would change the database.  (This SQL is only to illustrate what the Django script will do.  This SQL will not be part of the proposed solution.  The Django code will be based on the Django [Migrations](https://docs.djangoproject.com/en/2.0/topics/migrations/) documentation.)

``` sql
ALTER TABLE people_db_partytype ADD COLUMN petitioner BOOLEAN default 'f';
ALTER TABLE people_db_partytype ADD COLUMN pro_se BOOLEAN DEFAULT 't';
ALTER TABLE search_docket ADD COLUMN all_petitioners_pro_se BOOLEAN DEFAULT 'f';
```

Then, **modify** the existing Django code that analyzes and stores docket data.  
- **Add** code that sets each party's `petitioner` attribute.  For details about which types will be considered to be a petitioner, see the file [`party types that will be considered to be petitioners.md`](./party%20types%20that%20will%20be%20considered%20to%20be%20petitioners.md).
- **Add** code that sets the docket's attribute for `all_petitioners_pro_se` to true when a petitioner party's attorney's name is blank/empty, or when the petitioner's full name value is contained within the attorney's full name value or vice versa.
- **Add** code that sets a docket's `all_petitioners_pro_se` to true when all of the docket's parties that are petitioners are pro se.

*(Note:  This current proposal does not require a change to how PACER docket html is parsed into its component parts.  Instead, this proposal is about doing something new with the data that comes out of that parsing operation.  Accordingly, the proposed changes do not include any changes to Juriscraper and its parsing of that html in its PACER [docket_report.py](https://github.com/freelawproject/juriscraper/blob/master/juriscraper/pacer/docket_report.py) code.)* 

At a high level, the new Django code for analyzing the data will use the same sort of logic that is represented in the following SQL.  (This SQL will not be part of the proposed solution.  The Django code will not run this SQL.  This SQL is only to illustrate the sort of logic the Django code will do.)

``` sql
-- Select dockets and their petitioners and their attorneys where at least one of the docket's petitioners had representation
SELECT search_docket.id, people_db_partytype.name, people_db_party.name, people_db_attorney.name
FROM search_docket
INNER JOIN people_db_role      ON search_docket.id           = people_db_role.docket_id
INNER JOIN people_db_party     ON people_db_role.party_id    = people_db_party.id
INNER JOIN people_db_partytype ON people_db_role.party_id    = people_db_partytype.party_id
INNER JOIN people_db_attorney  ON people_db_role.attorney_id = people_db_attorney.id
WHERE people_db_partytype.name IN ('Plaintiff') -- {{{{see the link above for all the types that will be considered to be petitioners}}}}
AND EXISTS (
    SELECT 1
    FROM       people_db_role      people_db_role_sq
    INNER JOIN people_db_party     people_db_party_sq     ON people_db_role_sq.party_id    = people_db_party_sq.id
    INNER JOIN people_db_partytype people_db_partytype_sq ON people_db_role_sq.party_id    = people_db_partytype_sq.party_id
    INNER JOIN people_db_attorney  people_db_attorney_sq  ON people_db_role_sq.attorney_id = people_db_attorney_sq.id
    WHERE search_docket.id = people_db_role_sq.docket_id
    AND   people_db_partytype_sq.name IN ('Plaintiff') -- {{{{see the link above for all the types that will be considered to be petitioners}}}}
    AND   people_db_attorney_sq.name IS NOT NULL
    AND   people_db_attorney_sq.name != ''
    -- There are instances where a party's name is like "Mr. John Smith" and the related 
    -- attorney's name is "John Smith" (or vice versa).  So, to determine that a party had
    -- representation, we need to determine that both:
    -- The attorney's name is NOT within the party's name
    AND people_db_party_sq.name    NOT LIKE ('%' || people_db_attorney_sq.name || '%')
    -- AND the party's name is NOT within the attorney's name
    AND people_db_attorney_sq.name NOT LIKE ('%' || people_db_party_sq.name    || '%')
)
```

## Proposed solution: Solr

**Add** a field of type boolean that corresponds to the new search_docket table column `all_petitioners_pro_se'.  

Manually add the field to Solr's configuration files (rather than adding it, for example, via Django code).

The field would be represented as follows in the correct configuration file:

``` xml
<field name="all_petitioners_pro_se"
       type="boolean"
       indexed="true"
       stored="true"
       multiValued="false"/>
```

OTHER DETAILS T.B.D.

## Proposed solution: Already-stored docket data

Unless the already-stored docket data will be processed by the code described above -- *TO BE DETERMINED* -- , **create** a Django script that will iterate through all dockets that have already been stored and correctly set the boolean attributes described above.

## Proposed solution: Documentation

**Revise** the documentation to reflect the above changes.  The documentation consists of the CourtListener.com [FAQ](https://github.com/freelawproject/courtlistener/blob/master/cl/simple_pages/templates/faq.html) and "(?)" icon popups.

DETAILS T.B.D.

# Test cases

**Add** code for testing so that the dockets already being used in test cases can also be used for testing the new code.  

**Add** new test cases to do tests that are not already covered by those dockets.

DETAILS T.B.D.

TODO:  Find and examine exisiting test cases.  Incorporate the test cases referenced in Slack.  

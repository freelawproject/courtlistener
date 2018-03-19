**Proposed Change: Add a RECAP search option about representation.**

*This proposal stems from freelawproject/courtlistener issue #[806](https://github.com/freelawproject/courtlistener/issues/806).*

**CONTENTS**
- Problem statement
- Proposed solution by component
  - User Interface
  - Django code for parsing and storing docket data
  - Solr
  - Already-stored docket data
  - Documentation
- Test cases

# Problem statement

PACER and RECAP search users do not currently have an option to search for dockets where at least one petitioner had representation. Such dockets generally have higher quality complaints, motions, briefs, citations, and prose. Because that option is not available, searchers have to use other means that cost time and money to differentiate such cases from those where every petitioner is pro se.

# Proposed solution 

Enable a RECAP search option for retrieving dockets where at least one petitioner had representation.

Enabling the option requires changes in (1) the user interface, (2) the server-side Django code that parses and stores docket data, (3) the Solr search configuration, (4) the already-stored docket data, and (5) documentation.

The RECAP browser extension will not need to be changed.

## Proposed solution: User Interface

On the CourtListener.com [RECAP search page](https://www.courtlistener.com/recap/), **add** a select list to the search options.  The list's label will be: "At least one petitioner is represented".

**Provide** three select list options.  The first empty/blank value will be the default.
- ""
- "Yes"
- "No (Every party is pro se)"

Also, **add** a pop-up help tip, perhaps through a question-mark icon, with this text:
"Parties treated as petitioners include plaintiffs, appellants, applicants, complainants, claimants, and relators. If a party's name does not match the corresponding attorney's name, then the party is assumed to have representation, though this may not always be true."

## Proposed solution:  Django code for parsing and storing docket data

**Modify** the existing Django code that is for parsing and storing docket data.  Start with the code that contains a representation of the data model.

Within that code's representation of a docket, **add** a boolean attribute that will be used to identify whether the docket has a petitioner that is represented or not.  For that attribute, use a name like `petitioner represented`.  (Format the name with capitals, underscores, etc. as appropriate.)

The Django code will, in effect, change the data model and storage just like the following SQL would change the `search_docket` table.  (This SQL is only to illustrate what the Django script will do.  This SQL will not be part of the proposed solution.)

``` sql
ALTER TABLE search_docket ADD COLUMN petitioner_represented BOOLEAN DEFAULT 'f';
```

Then, **modify** the existing Django code that parses and stores docket data, including but not limited to the Juriscraper PACER [`docket_report.py`](https://github.com/freelawproject/juriscraper/blob/master/juriscraper/pacer/docket_report.py) file's code.  
- **Add** code that examines each docket party's type to determine if the party is a petitioner.  For more details about which types will be considered to be a petitioner, see the file [`party types that will be considered to be petitioners.md`](./party%20types%20that%20will%20be%20considered%20to%20be%20petitioners.md).
- When a petitioner party's full name value is contained within the attorney's full name value or vice versa, then the code will set the docket attribute for `petitioner represented` to true.
- At a high level, the Django script will use the same sorts of comparisons that are represented in the following SQL to determine whether a docket's `petitioner represented` attribute should be set to true.  (This SQL will not be part of the proposed solution.  The Django script will not run this SQL.  This SQL is only to illustrate the sorts of comparisons the Django script will do.)

``` sql
UPDATE search_docket 
SET petitioner_represented = TRUE
WHERE EXISTS ( -- at least one "petitioner" whose name is not within its attorney's name or vice versa
    SELECT 1
    FROM people_db_role
        ,people_db_party
        ,people_db_partytype
        ,people_db_attorney
    WHERE search_docket.id           = people_db_role.docket_id
    AND   people_db_role.party_id    = people_db_party.id
    AND   people_db_role.party_id    = people_db_partytype.party_id
    AND   people_db_role.attorney_id = people_db_attorney.id
    AND   (people_db_party.name       NOT LIKE ('%' || people_db_attorney.name || '%')
           OR people_db_attorney.name NOT LIKE ('%' || people_db_party.name || '%')
    AND   people_db_partytype.name  {{{{see the link above about types that will be considered to be petitioners}}}}
)
```

## Proposed solution: Solr

**Add** a field of type boolean that corresponds to the new search_docket table column 'petitioner_represented'.  

Manually add the field to Solr's configuration files (rather than adding it, for example, via Django code).

The field would be represented as follows in the correct configuration file:

``` xml
<field name="petitioner_represented"
       type="boolean"
       indexed="true"
       stored="true"
       multiValued="false"/>
```

OTHER DETAILS T.B.D.

## Proposed solution: Already-stored docket data

**Create** a Django script that will iterate through all dockets that have already been stored and correctly set each docket's new `petitioner represented` attribute.  To determine the value, The Django script will use the new code that is described in the sub-section above about docket parsing and storage.

## Proposed solution: Documentation

**Revise** the documentation to reflect the above changes.

DETAILS T.B.D.

QUESTION:  Where is this documentation? (URL(s) are needed, please)

# Test cases

**Add** code for testing so that the dockets already being used in test cases can also be used for testing the new code.  

**Add** new test cases to do tests that are not already covered by those dockets.

DETAILS T.B.D.

TODO:  Find and examine exisiting test cases.  Incorporate the test cases referenced in Slack.  

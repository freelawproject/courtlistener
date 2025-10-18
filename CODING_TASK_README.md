### Ali Klemencic

Coding Task for Open Data Backend Developer


# 1. High-Level Scraping Plan

## Enumeration Strategy

In my research, I found that California Supreme Court cases generally fall into two categories: modern cases (ACIS) and legacy cases (pre-ACIS). Modern cases, which begin around 1987, follow a consistent case number format (`Sxxxxx`) and are searchable through [ACIS](https://appellatecases.courtinfo.ca.gov). Legacy cases use a variety of letter prefixes based on location or case type (e.g., `Crim.` or `L.A.`) and are not available in ACIS.  

[FindLaw](https://caselaw.findlaw.com) provides several useful resources for case discovery. You can browse California Supreme Court [cases by year](https://caselaw.findlaw.com/court/ca-supreme-court/years) or use a [blank search to access an aggregate list](https://caselaw.findlaw.com/search.html?search_type=party&court=ca-supreme-court&text=&date_start=&date_end=). These resources are helpful for obtaining both modern case numbers and data for pre-ACIS cases. Additionally, external sources, including news sites or AI-assisted searches, may be used to supplement docket information for legacy cases when official records are incomplete.


### Modern Cases (ACIS “S” Numbers)

### Modern Cases (ACIS)

Modern California Supreme Court cases follow a sequential case number format (`Sxxxxx`). While it is theoretically possible to enumerate cases by incrementing numbers, this approach would be time-consuming and inefficient. Instead, I would iterate through [FindLaw's Supreme Court cases by year](https://caselaw.findlaw.com/court/ca-supreme-court/years), extracting all case numbers that begin with `S`. For each case number, I would submit the [ACIS search form](https://appellatecases.courtinfo.ca.gov/search.cfm?dist=0), select the "Docket" tab, and parse the resulting page for relevant docket information to associate with that case number. If the page indicates "No case found," the case would be marked as missing and the process would continue.  

Because the resulting URLs include time-sensitive token information, I would maintain a valid cookie jar and refresh it periodically to prevent expired sessions. Randomized delays between requests would help avoid detection by anti-bot measures.  

Scraping would be parallelized and batched, using 2–4 concurrent workers, each handling non-overlapping years of case numbers. Requests would be throttled to below one per second per IP to respect rate limits. Every successful fetch would log the case number, year, and timestamp to allow resumption in case of interruption, while unsuccessful attempts would also be logged for later verification or retries. Periodically—approximately every five years of case data—I would verify that retrieved data is valid.  

For cases present on FindLaw but not found in ACIS, the legacy scraping process would be followed to capture their docket information.


### Legacy Cases (Pre-ACIS)

### Legacy Cases (Pre-ACIS)

For cases that do not exist in ACIS, I would extract relevant information from their [FindLaw](https://caselaw.findlaw.com/court/ca-supreme-court/years) pages. Since legacy case numbers use a variety of letter prefixes (e.g., `L.A.`, `Crim.`), I would normalize them in a `CaseIdentifier` database—standardizing variations such as `L.A.` and `LA` to a consistent format and removing extraneous spaces.

FindLaw pages often present case information as dense text, so I would parse these pages to extract key metadata, such as decision dates, parties, and opinion summaries, effectively creating a custom docket representation. To maintain consistency, I would cross-reference this data with any ACIS records and defer to ACIS information in cases of duplication, using both exact case number matching and fuzzy matching of case titles to handle instances where multiple numbers are assigned to a single case.  

Additionally, I would validate and enrich this data by cross-referencing archival sources such as the California Reports, LexisNexis, and available opinion PDF archives, ensuring maximum coverage and accuracy for pre-ACIS cases.

## Risks and Challenges

### Incomplete Data

Some cases are missing from online archives, resulting in gaps in coverage, and pre-1987 cases may not have docket pages in ACIS at all, meaning early cases often exist only as opinion PDFs or citation metadata. Even for cases present online, gaps in opinion–docket linkage occur when an opinion lacks a working “View Docket” link, and opinion-only data provides limited metadata, which should be flagged as “pre-docket era”. Document access can also be inconsistent: older opinions may link to dead URLs, linked PDFs or briefs may move or expire, and some docket numbers may never have public pages due to being sealed, withdrawn, or confidential. Enumeration can miss case numbers that were never assigned or skipped, creating additional coverage gaps. To mitigate these issues, I would supplement ACIS data with external sources like LexisNexis or FindLaw, cross-reference docket numbers from opinion headers, maintain logs of missing or suspicious gaps, archive local copies of documents when first seen, and periodically retry or refresh broken links. This approach allows partial coverage while systematically addressing known holes in the dataset.

### Mismatched Data

Different numbering systems prevent direct joins between modern S-series cases and legacy cases, requiring matching by case title and decision date. Variations in case title spelling can lead to join errors, which can be mitigated using fuzzy matching and normalization. Duplicate or inconsistent docket data occurs when different pages or versions present slightly different event lists or order; these can be handled by deduplicating based on event date, description, and sequence, merging incremental updates conservatively, and retaining full provenance. Legacy numbering inconsistencies, such as variations in “L.A.” or “Crim.” formats, should be normalized using regex and stored in a dedicated table. Finally, data quality issues—like inconsistent formatting, missing dates, OCR errors, nonstandard numbering, or scanned-only pages—necessitate robust fallback parsers, heuristics to fill missing fields, and logging or manual review of anomalies to ensure accuracy.

### Rate Limiting and Bot Blocking

Crawling ACIS requires careful management of rate limits and anti-bot protections. The site likely enforces search and request throttling, and excessive queries may trigger timeouts, IP blocking, CAPTCHAs, or HTTP 429 responses. To avoid these issues, I would implement request throttling (e.g., 1–2 requests per second), randomized delays, and exponential backoff on failures, while respecting robots.txt and session cookies. Persistent sessions should be maintained, and request_tokens refreshed periodically (e.g., every 50–100 cases). For larger-scale crawling, IP rotation and caching of previously retrieved results can help prevent blocking, while conservative concurrency and polite crawling behavior reduce the risk of triggering anti-automation defenses.

### Site Changes

Scrapers for ACIS must be resilient to site and schema changes, as minor HTML, JavaScript, or UI updates can break parsers. To handle this, I would use modular, versioned parsing logic with robust CSS/XPath selectors and fallback patterns, along with monitoring to detect anomalies or spikes in errors.

### Policy Concerns

Some cases, such as sealed matters, juvenile cases, or attorney discipline files, may not appear in searches or be publicly accessible; I would respect this, log it, and move onto the next case. Even for publicly available data, I would make sure to comply with court terms of use, the California Public Records Act, and any redistribution or storage restrictions. I would build the crawlers to operate politely to avoid overloading the site, implement throttling, and detect access-denied or blank sections. For bulk historical access, I might need to coordinate with court staff or seek official channels to ensure full compliance.

### Resource Concerns

Enumerating the full set of California Supreme Court cases can be resource-intensive, as brute-forcing large numeric ranges could generate many “not found” requests and consume significant bandwidth and time. To mitigate this, I would prioritize search-based listings, seed from external sources, skip obviously empty ranges, batch candidate testing, cache negative results, and dynamically adjust ranges. Additionally, synchronization and concurrency hazards—such as race conditions when crawling overlapping datasets or updating partial records—require careful handling using job queues, idempotent updates, locking, and versioning to ensure data consistency and efficient resource use.
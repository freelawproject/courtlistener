"""Build the mapping the fix_ca4_govinfo_pdfs command consumes.

Kept for provenance: it records how the mapping was derived, so it can be
audited or rebuilt rather than taken on trust. The mapping itself is attached to
issue 8100 rather than committed here, since it is a one-time artefact.

Its two inputs are not in this repository. They are the outputs of the offline
audit of issue 8100, which reads every affected record's GovInfo MODS metadata.
Put affected.csv and resolution.csv beside this script to re-run it.

Joins affected.csv (what the database holds) with resolution.csv (which granule
each record should point at). Only `resolved` rows are emitted: the other
verdicts need a maintainer decision and are listed in manual_decisions.md.

`expected_status` carries the status the audit read from the package's MODS
subTitle. The command derives the status from the replacement PDF's own banner
and refuses to write it when the two disagree, so this column is what keeps the
status change auditable rather than re-derived by the rule that caused the bug.
An empty value means the subTitle stated neither PUBLISHED nor UNPUBLISHED.

The two false positives are excluded. Their clusters hold a second opinion whose
text date does match date_filed, so GovInfo re-released granule 0 rather than
the scraper picking the wrong part. They are also the only resolved rows whose
chosen granule is part 0, and the command rejects a whole file that contains
one, so re-admitting either would abort the run rather than skip the row.
"""

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FALSE_POSITIVE_CLUSTERS = {"10786785", "10879884"}

# Peltier v. Charter Day School. Repairing these two would give them the same
# download_url as opinions 11058394 and 11058393, which the fixed scraper
# created on 2025-05-23 from the very same GovInfo granules. The files are
# byte-identical, so `find_and_merge_versions` would fire, and it makes the
# opinion it just extracted the main version. That means the repaired 2022
# record would win and the 2025 record, whose cluster carries 41 citations,
# would drop out of Elasticsearch. Which record should survive is a judgement
# call, so these are held back for manual handling.
HELD_BACK_OPINIONS = {"7375595", "7375594"}

csv.field_size_limit(sys.maxsize)

with (HERE / "affected.csv").open(newline="") as fh:
    affected = {r["opinion_id"]: r for r in csv.DictReader(fh)}

rows = []
with (HERE / "resolution.csv").open(newline="") as fh:
    for r in csv.DictReader(fh):
        if (
            r["verdict"] != "resolved"
            or r["cluster_id"] in FALSE_POSITIVE_CLUSTERS
            or r["opinion_id"] in HELD_BACK_OPINIONS
        ):
            continue
        db = affected[r["opinion_id"]]
        rows.append(
            {
                "opinion_id": r["opinion_id"],
                "expected_download_url": db["download_url"],
                "expected_sha1": db["sha1"],
                # db["package"] is the audited package id, so the URL is built
                # from it rather than from splitting the granule id.
                "new_download_url": (
                    f"https://www.govinfo.gov/content/pkg/{db['package']}"
                    f"/pdf/{r['chosen_access_id']}.pdf"
                ),
                "expected_status": r["mods_status"],
            }
        )

if not rows:
    raise SystemExit("no resolved rows to emit; check resolution.csv")

out = HERE / "ca4_govinfo_repair.csv"
with out.open("w", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(f"wrote {len(rows)} rows to {out}")

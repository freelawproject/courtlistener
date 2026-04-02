import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cl.settings")

import django

django.setup()

import json

from cl.search.models import Citation

expected = {
    "333": 23, "334": 31, "335": 24, "336": 20, "337": 35,
    "338": 26, "339": 24, "340": 22, "341": 29, "342": 27,
    "343": 28, "344": 29, "345": 19, "346": 28, "347": 27,
    "348": 27, "349": 23, "350": 31, "351": 25, "352": 26,
    "353": 23, "354": 12,
}

total_exp = total_act = 0
for vol, exp in sorted(expected.items(), key=lambda x: int(x[0])):
    actual = Citation.objects.filter(reporter="Conn.", volume=vol).count()
    status = "OK" if actual >= exp else f"MISSING {exp - actual}"
    print(f"  {vol} Conn.: expected={exp}, actual={actual} {status}")
    total_exp += exp
    total_act += actual
print(f"\nTotal: expected={total_exp}, actual={total_act}")

# Load expected pages from metadata
with open("/opt/courtlistener/conn-partitioned-metadata.json") as f:
    metadata = json.load(f)

# Build expected citations per volume: set of pages
expected_pages: dict[str, set[str]] = {}
for item in metadata:
    cit = item.get("citation", "")
    if " Conn. " not in cit:
        continue
    vol, page = cit.split(" Conn. ")
    expected_pages.setdefault(vol, set()).add(page)

# Check 333 Conn. — find missing
for vol in ["333", "335"]:
    db_pages = set(
        Citation.objects.filter(reporter="Conn.", volume=vol).values_list(
            "page", flat=True
        )
    )
    meta_pages = expected_pages.get(vol, set())

    missing = meta_pages - db_pages
    extra = db_pages - meta_pages

    if missing:
        print(f"\n{vol} Conn. — missing pages (in metadata but not in DB): {sorted(missing, key=lambda x: int(x))}")
    if extra:
        print(f"\n{vol} Conn. — extra pages (in DB but not in metadata): {sorted(extra, key=lambda x: int(x))}")

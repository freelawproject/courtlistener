# Test Suite Performance Audit

Goal: reduce test-suite wall-clock time by removing redundant tests, fixing
disproportionately slow tests, and eliminating tests that interfere with each
other — **without changing the functionality under test**.

## Method

- Analysis is module-by-module (module = Django app), heaviest first by test LOC.
- Grounded in a profile of an actual suite run (`fullspeed.scope` / `speed.scope`,
  speedscope format). Hard data: **Postgres `wait` dominates self-time (~15s)** —
  i.e. DB round-trips from object creation — followed by heavy ORM instantiation
  (`get_deferred_fields`), Faker data generation (`random_elements`/`choices`),
  eyecite tokenizer regex compilation, and template rendering. ES index rebuilds
  are also expensive.
- Therefore the dominant levers are: **create fewer DB rows, and create them less
  often** (`setUp`→`setUpTestData`, `create()`→`build()`, trim factory counts,
  `TransactionTestCase`→`TestCase`), reduce Faker usage, share ES index builds,
  and reclassify pure-logic tests off DB-backed base classes.

Impact = HIGH/MED/LOW wall-clock payoff. Effort = S/M/L. Line numbers are from the
state of the repo at audit time; re-verify before editing.

> Caveat: findings are from static analysis + the existing profile, not a fresh
> per-test timing run (the suite is too slow to re-run repeatedly). "Verify before
> changing" items may encode intentional coverage (version parity, commit semantics).

---

## Module 1 — `search` (31k lines / 18 files)

Almost all avoidable cost is object creation running more often than needed, plus
a layer of selenium and redundant test methods.

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| Pure-function tests on DB-backed `TestCase` (pay txn setup/teardown for nothing) | `test_docket_number_cleaner.py:34-122` (`TestCleanDocketNumberRaw`); `tests_semantic_search_opinion.py:835-941` (3 form/validation/gate classes) | Switch to `SimpleTestCase` (verify `SearchForm.is_valid()` doesn't hit DB) | S |
| Redundant selenium tests (real Chrome + per-test full ES opinion reindex + 4 JSON fixtures) | `tests.py:1662-2073` (`OpinionSearchFunctionalTest`, 6 methods) | `test_query_cleanup_integration` (1688-1699) is fully covered by pure-Python `test_query_cleanup_function` (1026-1152) → **delete**. Audit other 5 vs non-selenium SERP coverage. Also kills deprecated JSON fixtures | L |
| ~27 single-assertion `*_filter` tests on a read-only shared index; API common set runs **twice** (V3+V4 inheritance) | `tests_es_recap.py:531-557, 627-700, 3801-3998` | Merge into `subTest()`-driven loops → ~25 fewer method setups/teardowns, zero coverage loss | M |
| Excessive factory data — `setUpTestData` builds ~104 rows; one test needs only 3 | `test_pacer_bulk_fetch.py:52-129` | Trim to minimum each assertion needs | M |
| 4 heavy fixture mixins just to count a handful of rows | `test_v2_pages.py:306-421` (`HomepageStatsTest`) | Replace `RECAPSearchTestCase, CourtTestCase, PeopleTestCase, SearchTestCase` with minimal `setUpTestData` | M |

### MED impact

- **`TransactionTestCase` → `TestCase` + `captureOnCommitCallbacks`** (verify on-commit ES signals still fire): `EsOpinionsIndexingTest` (`tests_es_opinion.py:3679`), `OralArgumentIndexingTest` (`tests_es_oral_arguments.py:2887`), `PeopleIndexingTest` (`tests_es_person.py:2059`). They rebuild their full corpus on *every* test because rollback doesn't apply — largest repeated-creation pattern if convertible.
- **`rebuild_index()` then immediately empty it** (populate thrown away): `tests_es_person.py:2001` (`IndexJudgesPositionsCommandTest`), `tests_es_opinion.py:3461`. Replace with bare `create_index()`.
- **`setUp` → `setUpTestData`** for read-only shared rows: `tests.py:111-136` (`ModelTest`), `test_clean_docket_number_raw.py:9-69`, `test_docket_number_cleaner.py:129-141 & 652-691`, `test_search_signals.py:44-87` (reuse one `recap_doc` across subTest cases).
- **Shrink oversized text blobs** feeding token-counter/eyecite to just over each threshold: `test_generate_opinion_embeddings.py:57-149`.

### Correctness bugs surfaced (fix regardless of perf)

- `tests_es_recap.py:3668-3681` — decay-relevancy V3/V4 tests **mutate shared `cls.test_cases` dicts in place**; fragile ordering dependency. Use `{**test["search_params"], "type": ...}`.
- `tests_es_oral_arguments.py:1490-1497` — `test_oa_combine_search_and_filtering` builds new `search_params` but **never issues the request**; re-asserts on stale response. The `argued_after`/`minimum_should_match` case is silently untested at the frontend.

### Dead code / quick cleanups

- Duplicate `rebuild_index("alerts.Alert")` in 3 OA classes (`:506/509, 948/951`); duplicate identical request block `tests_es_oral_arguments.py:1113-1120`; empty `@override_settings()` (`tests.py:1658`); no-op `setUpClass` (`tests_es_parenthetical.py:174-176`).

### Verified non-issues (don't waste effort here)

- `test_docket_number_cleaner.py` vs `test_clean_docket_number_raw.py` are **NOT redundant** — one unit-tests functions, the other tests the management command end-to-end. Misleading names only.
- `time.sleep` in `test_pacer_bulk_fetch.py` is **already `@patch`-mocked** at all 4 sites — no real wall-clock waste.
- `tests_es_oral_arguments.py` has **no VCR/sleep** despite initial flag.

**Bottom line:** biggest single win is the `TransactionTestCase`→`TestCase` conversions (if signals permit). Lowest-risk wins are the `SimpleTestCase` reclassifications and the `rebuild_index`-then-empty fixes. Selenium consolidation is high payoff, higher effort.

---

## Module 2 — `recap` (13.2k lines / 2 files)

No `TransactionTestCase`, no ES rebuilds, no Django fixtures in either file — so the
entire opportunity is `setUp`→`setUpTestData`, fixture-read caching, and dropping
debug prints. (24 `setUp` uses, but most are already correct or hold per-test
mutated state.)

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| `mock_bucket_open` re-reads PDF/HTML fixtures from disk on **every** mock call, every test | `tests.py:3894` (used across both files) | Cache with `functools.lru_cache` keyed on `message_id` (return bytes), or read once at module load | S |
| `setUp` rebuilds 3 courts/3 dockets/3 entries/3 RDs/3 FQs **per test** (~7 tests); only mutates via `self.rd.save()` (rolled back) | `tests.py:3209-3290` (`RecapPdfFetchApiTest`) | Move all creation to `setUpTestData`; delete the now-unnecessary `is_available`-resetting `tearDown` (3292) | M |
| Same pattern, ~5 tests | `tests.py:3593-3664` (`RecapAttPageFetchApiTest`) | Move to `setUpTestData` | M |
| `setUp` re-saves 2 Users + 2 UserProfiles (4 writes) on **every** test (~33 tests) with static field values | `test_recap_email.py:347-370` (`RecapEmailDocketAlerts`) | Set the fields in `setUpTestData` (187-188); ~130 redundant writes removed | M |
| Debug `print(pq.__dict__)` left in a test — spams stdout | `tests.py:4202` (`RecapZipTaskTest`) | Delete the line | S |

### INTERFERENCE (shared-state mutation across tests — fix regardless of perf)

- `test_recap_email.py:83,92,102` — `RecapEmailToEmailProcessingQueueTest` mutates `cls.data` in place (`self.data["court"]="scotus"`, `del self.data["mail"]["headers"]`). `setUpTestData` doesn't deep-copy plain dicts → leaks across tests, order-dependent. Fix: `copy.deepcopy(self.data)` in `setUp`, or build it in `setUp`.
- `test_recap_email.py:2744-2745,2818,2884` — `self.acms_email_data.copy()` is **shallow**; then mutates a nested `["dockets"][0]["docket_entries"][0]` → corrupts shared class dict across 3 ACMS tests. Fix: `copy.deepcopy`. (Also `email_data = email_data =` double-assign typos at 2744/2884.)

### MED impact

- **`setUp`→`setUpTestData` (split DB objects out, keep mutated dicts in `setUp`):** `tests.py:4454-4501` (`TerminatedEntitiesTest`), `tests.py:4250-4274` (`RecapAddAttorneyTest`), `tests.py:8781-8793` (`BadRedactionCheckTest`, also delete redundant `Docket.objects.all().delete()` tearDown).
- **REDUNDANT pairs mergeable via `subTest()`** (changes failure granularity — confirm team accepts): `test_recap_email.py` NEF/NDA auto-subscription pairs (380-446 vs 1641-1700; 595-648 vs 1717-1767); magic-number sealed/unsealed (2142-2178 vs 1960-2028); sealed-entry with/without attachments (2247-2319 vs 2331-2413).
- **Build factory payloads once:** `test_recap_email.py:2262-2668` — `RECAPEmailNotificationDataFactory` (Faker-heavy) + throwaway `CourtFactory` built inside ~5 async test bodies with static shapes → move courts to `setUpTestData`, build static payloads once.

### LOW / cleanup

- `self.user = User.objects.get(username="recap")` repeated in 11 `setUp`s (`tests.py:285,2584,3846,…`) — fetch once as `cls.user` in `setUpTestData`.
- Debug `print(f"Testing CSV parser…")` at `tests.py:6108`.
- `GetAndCopyRecapAttachments.setUpTestData` (`test_recap_email.py:2932-2975`) could `bulk_create` 9 RDs.

### Verified safe to leave (do NOT touch)

- PQ-file-consuming classes (`RecapDocketTaskTest` 5018, attachment/claims/appellate/criminal task tests): `setUp` reads an HTML/PDF asset whose `filepath_local` is consumed/mutated by `process_recap_*` — genuinely per-test. Courts already in `setUpTestData`.
- `RecapPdfTaskTest` (4000), `RecapZipTaskTest` (4153): objects `.delete()`d inside tests — risky to hoist.
- Many classes already use `setUpTestData` correctly (`RecapUploadsTest`, `LookupDocketsTest`, etc.).
- No true duplicate/dead tests in `tests.py`.

**Bottom line:** biggest wins are the `mock_bucket_open` fixture caching (touches many tests cheaply) and the `RecapEmailDocketAlerts` / `RecapPdfFetchApiTest` / `RecapAttPageFetchApiTest` `setUp`→`setUpTestData` conversions. Two real shared-dict-mutation bugs worth fixing on correctness grounds alone.

---

## Module 3 — `alerts` (10.9k lines / 3 files)

Both percolator test classes are **already** `TestCase` + `captureOnCommitCallbacks`
(no `TransactionTestCase` lever here). Scope correction: `tests_recap_alerts.py`
has **no VCR cassettes** despite the grep flag. Dominant cost = **per-test ES/percolator
index drop+recreate** + Postgres factory churn inside repeated `call_command` sweeps.

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| `setUp` does `RECAPPercolator._index.delete(); .init()` (full index drop+recreate) on **every** test (~16) | `tests_recap_alerts.py:2797-2799` | Create mapping once in `setUpClass`; in `setUp` only `delete_by_query match_all` the percolator **docs** | M |
| Same per-test percolator drop+recreate (~8 tests) | `tests_opinion_alerts.py:148-157` (`OpinionPercolator`) | Create index in `setUpClass`/`setUpTestData`; clear docs per test | M |
| Lone selenium test spins up Chrome+StaticLiveServer+ES just to assert a sign-in redirect + flash message (edit logic already covered by async tests at 571, 805) | `tests.py:1030-1078` (`AlertSeleniumTest.test_edit_alert`) | Replace with `self.async_client` test asserting redirect + flash text; drop selenium | M |
| Fixture-free logic tests parked in heavyweight ES/webhook classes — pay `rebuild_index` + audio/profile factory setup for nothing | `tests.py:1706-1717` (`test_long_alert_subjects_truncation`), `tests.py:1991-2015` (`test_is_match_all_query`), `tests.py:2017-2037` (`test_clean_query`) | Move to `SimpleTestCase`/lightweight `TestCase` | S |
| Two `test_case_only_alerts` (~340 lines each) build identical corpus+assertions, differ only by send command | `tests_recap_alerts.py:2335-2675` vs `4804-5050+` | Extract shared helper parametrized by send-mechanism; two thin methods | M |

### MED impact

- **Per-test `delete_index`+`create_index`** on `alerts.Alert` despite `ELASTICSEARCH_DISABLED=True`: `tests.py:4206-4260` (`SearchAlertsIndexingCommandTests`, ~3 tests). Move recreate to the 2 indexing tests only.
- **Redundant `tearDown`/`tearDownClass` blanket deletes** (`Alert.objects.all().delete()` etc.) — transaction rollback already handles these; extra Postgres round-trips that can clobber `setUpTestData` rows mid-class: `tests.py:156-157, 879-882, 1094-1095, 2069-2070` (verify audio ES docs cleanup at 2908-2909 before removing).
- **Duplicate-corpus pairs** mergeable via shared builder: `tests_recap_alerts.py:1548-1797` vs `3712-4020` (limit-per-alert vs group-percolator).
- **`RestartSentEmailQuotaMixin` absent** on email-sending classes (`tests.py` `SearchAlertsOAESTests`/`SearchAlertsWebhooksTest`, `tests_opinion_alerts.py`) → `email:*` Redis keys may leak across classes → order-dependent quota failures. Mix it in (verify backend).
- Batch object creation into fewer `captureOnCommitCallbacks` blocks (each forces a separate ES flush): `tests_recap_alerts.py:248-477`.

### INTERFERENCE (correctness)

- `tests_recap_alerts.py:102-106, 2101` — `rebuild_percolator_index` permanently mutates class-level `RECAPPercolator._index._name = "recap_percolator_sweep"` (never restored) → order-dependent percolator pollution. Restore in `addCleanup`/`finally`.
- Many per-test `docket.delete()` cleanups (`tests_recap_alerts.py:474-476, 802, …`) are skipped on early assertion failure → leak docs into the class-shared index → cascading failures. Move to `addCleanup(...)`.

### Verify

- `tests_opinion_alerts.py:77` — `rebuild_index("alerts.Alert")` in `setUpTestData` looks redundant given the per-test `OpinionPercolator` reinit at 149.

**Bottom line:** the single biggest cross-module win is eliminating per-test ES/percolator index recreation (here: `tests_recap_alerts.py:2797`, `tests_opinion_alerts.py:148`, `tests.py:4258`) — replace with one-time class-scoped creation + cheap per-test doc clear. The monolithic sweep tests accumulate state across `call_command` calls so are NOT freely splittable.

---

## Module 4 — `corpus_importer` (7.6k lines / 3 files)

No `TransactionTestCase` anywhere. **All 16 `time.sleep` calls are MOCKED** — zero
wall-clock waste (verdict below). Wins are redundant teardown deletes + a per-test
re-parse.

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| `setUp` runs `process_docket_data()` (XML parse + many DB writes) before **every** test; `tearDown` does 4× `Model.objects.all().delete()` which deletes the `setUpTestData` docket → create-once benefit destroyed | `tests.py:513-543` (`PacerDocketParserTest`) | Move parse to `setUpTestData`; drop blanket `delete()` tearDown (rollback handles it); split `test_get_and_save_free_document_report` (606, doesn't use parsed data) into a lighter class | M |
| Redundant `Docket.objects.all().delete()` in `tearDown` — defeats transaction rollback, pure wasted round-trips per test | `tests.py:1571, 2285` (`HarvardMergerTests`, `ColumbiaMergerTests`) | Delete the tearDown line; keep `patcher.stop()` (or `addCleanup`) | S |

### MED / LOW

- `test_scotus_daemon.py:591-601` — `CourtFactory(id="scotus")` in `setUp` though never changes → move to `setUpTestData`. (Rest of this file is well-structured: `SimpleTestCase` for pure logic, symmetric Redis cleanup.)
- `tests.py:4080-4096` (`ScrapeIqueryPagesTest.setUp`) — Redis cleanup only in `setUp`, no symmetric tearDown → ordering/leak risk. Mirror in tearDown or use test-scoped prefix.
- Merger tests embed large inline XML/HTML constants + a per-test factory cluster; near-duplicate bodies mergeable via `subTest()` (MED/L, verify distinct DB state first).
- `test_scotus_daemon.py` — same ~5-patch stack copy-pasted across ~7 tests; extract a contextmanager helper (readability).

### Dead code

- **`import_columbia/html_test.py` is NOT a test file** — a one-off dev script with `os.chdir("/home/elliott/freelawmachine/...")`, no test classes. Never collected by `manage.py test` (matches `test*.py`, not `*_test.py`) → zero suite cost today, but dead/duplicated and a landmine for any pytest migration. Delete or move out of the test tree.

### `time.sleep` verdict

All 16 MOCKED, none waste wall-clock:
- `tests.py:651, 707, 739` — `@patch("...scrape_pacer_free_opinions.time.sleep")`.
- `tests.py:4337, 4381, 4426, 4804, 4817, 4884, 4908, 4975, 4995, 5069, 5417, 5453, 5492` — `with patch("cl.lib.decorators.time.sleep")`.

**Bottom line:** the `time.sleep` flag was a false alarm. Real wins are the redundant `objects.all().delete()` teardowns and `PacerDocketParserTest`'s per-test re-parse.

---

## Module 5 — `api` (5.5k lines / 2 files)

No `TransactionTestCase`. Two dominant costs: ~40 near-identical pagination endpoint
tests, and per-test user/token creation in throttle suites. Also: heavy JSON-fixture
reliance (violates CLAUDE.md "never use fixtures").

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| ~40 `test_*_endpoint` methods are 1:1 wrappers around `_base_test_for_v4_endpoints`/`_test_v4_non_cursor_endpoints` differing only by a param dict; each pays full setup + several DB-backed `make_client` calls | `tests.py:2543-3008` (`V4DRFPaginationTest`) | Move (endpoint, ordering, …) tuples to a class list; iterate in 1-2 `subTest` loops. Identical assertions | M |
| `make_client(...)` (builds a DB Token) called **inside** nearly every async test | `tests.py:2108, 2982, 3982, 4173, 4231, 4278, 4292, 4348, 4411` | Build one client in `setUpTestData`/`setUp` and reuse | S |
| 7 classes load JSON fixtures (`judge_judy.json`, `recap_docs.json`, …) — per-class DB cost + blocks `setUpTestData` sharing; also a policy violation | `tests.py:174-178, 386-389, 888, 1183, 1374, 1819-1822, 1973-1976` | Replace with FactoryBoy in `setUpTestData` | L |

### MED / LOW

- Per-test `UserFactory()`/`APIThrottleFactory()` in throttle suites (~30 tests): `tests.py:4785-4991, 5002-5180, 5184-5328`. Share `cls.user` in `setUpTestData` where the test doesn't mutate throttles (~15 safe; verify each).
- `tests.py:400-421` (`ApiQueryCountTests.setUp`) — recreates user+perms+PQ+Audio every test for read-only query-count tests; move to `setUpTestData`, drop the `UserProfile.objects.all().delete()` tearDown (420-421, also a cross-test state nuke).
- `tests.py:3095-3150` (`test_avoid_sending_webhooks_to_internal_ips`) — 3 copy-paste blocks mergeable via `subTest`; **also a latent bug**: asserts on `webhook_event.response` instead of `_2`/`_3`.
- `test_replica_routing.py:84` (`ReplicaRoutingMiddlewareTest`) — touches no ORM but extends `TestCase` (unused per-test transaction × 11 tests). Switch to `SimpleTestCase` (verify `@override_flag` waffle lookup doesn't hit DB).

**setUp tally:** of 18 `setUp` uses, only **1** (`ApiQueryCountTests`) is a clean mechanical move; the bigger win is method-body factory hoisting in throttle suites + the pagination collapse. Redis is well-managed (no leaks found).

**Bottom line:** collapse the 40 pagination tests + reuse one `make_client` = the biggest win; fixture→FactoryBoy is high-value but high-effort and also a policy fix.

---

## Module 6 — `users` (4.5k lines / 1 file)

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| All 7 tests are `async_client` HTTP tests but class extends `LiveServerTestCase` (= `TransactionTestCase`: table truncation, no rollback, live-server thread) | `tests.py:119` (`UserTest`) | Change base to `TestCase`; drop `self.live_server_url` string prefixes (client ignores host) | M |
| Same — 9 `async_client` tests, no browser needed, paying TransactionTestCase tax | `tests.py:295` (`UserDataTest`) | Change base to `TestCase`; remove `live_server_url` prefixes | M |
| 2 selenium tests (password reset/set) behind `BaseSeleniumTest` whose `setUp` rebuilds the audio ES index + reindexes opinions every test — unrelated to password reset; neither test exercises JS | `tests.py:899` (`LiveUserTest`) | Rewrite both as HTTP-client tests on a plain `TestCase` (preserve outbox + redirect asserts), then delete the class — kills a Chrome boot + ES rebuild | S |
| `test_add_bcc_random` calls `add_bcc_random` **2,000,000 times** (4 rates × 50 × 10_000) to verify a probability | `tests.py:2417` | Cut to ~1_000 iters × 5 loops with widened tolerance, or seed RNG for deterministic exact-count asserts | S |

### MED / LOW

- `tests.py:562` (`test_generate_recap_dot_email_addresses`) — uses `create()` for 2 profiles to test a pure string property; use `.build()` (no DB).
- **Leaked Redis prefixes** (mixin only clears default `email` prefix): `tests.py:2570` (`test-email-counter`), `2595/2637` (`test-emergency-break`, `test-mass-email`) — add `self.addCleanup(self.restart_sent_email_quota, "<prefix>")`.
- `tests.py:3559` (`WebhooksHTMXTests.tearDown`) — redundant `Webhook.objects.all().delete()` under rollback (also wrong `def tearDown(cls)` signature).
- `tests.py:75 & 98` — duplicate `UserProfileWithParentsFactory` import.

**Bottom line:** reclassifying `UserTest`/`UserDataTest` off `LiveServerTestCase` (16 tests off TransactionTestCase) + deleting the 2 browser tests + cutting the 2M-iteration loop are the big wall-clock wins.

---

## Module 7 — `citations` (3.6k lines / 1 file)

### `tokenizer cost` — verified NON-issue

The eyecite tokenizer is **constructed once** (`HYPERSCAN_TOKENIZER` module-level at
`tests.py:104`) and shared by every `get_citations(...)` call. eyecite caches `_db`
per-instance **and** on disk (`.hyperscan/`), so the profiled `convert_regex`/
`hyperscan_db` cost is a one-time process build, NOT per-test. **Do not "optimize"
the tokenizer — there is no speedup there.** The real cost is Postgres + ES.

### HIGH / MED impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| ~22 `OpinionClusterWith*` `create()`s + 6 `Citation.create` + 2 `rebuild_index` + full reindex in one class setup — dominant DB+ES cost in the file | `tests.py:705-1022` (`CitationObjectTest.setUpTestData`) | Audit for genuinely-unused `citationN`/`cluster_N` fixtures and prune (already correctly in `setUpTestData`) | M |
| `ESIndexTestCase, TransactionTestCase` — truncation, no rollback, much slower | `tests.py:3516-3574` (`ReindexESCiteFieldsTest`) | Verify transactional behavior is required (uses `.update()` + reindex); if not, downgrade to `TestCase` | M |
| `TransactionTestCase` + `get_citations` at class-definition time mutating shared mutable lists; `UnmatchedCitation.objects.all().delete()` hints at leakage | `tests.py:3161` (`UnmatchedCitationTest`) | Move `get_citations` into `setUpClass`; verify TransactionTestCase needed (tests a `post_save` signal — likely fine as `TestCase`) | M |
| 5 `CitationCommandTest` tests run the full `find_citations` command over the same fixture with identical post-conditions | `tests.py:1746-1856` | Collapse to one `subTest`-driven test iterating CLI arg-sets, resetting count between | S |
| Separate ES class with its own `rebuild_index` + full reindex for a single test | `tests.py:631-674` (`RECAPDocumentObjectTest`) | Merge its setup into a shared opinion-citation ES base to amortize one index build instead of three | M |

### LOW

- `tests.py:1670-1687` (`test_citation_string_volume`) — `create()` for a no-DB string assertion duplicating `test_saving_volume_string` (3309); use `build()` or fold in.
- Verify signal-receiver cleanup is in `finally`/`addCleanup`: `tests.py:1607-1648` (`test_signal_disconnection` mutates `post_save.receivers`).
- Pure-logic `SimpleTestCase` classes (`FilterParenthetical`, `DescriptionScore`, `GroupParentheticals`, 1859-2449) are already DB-free + table-driven — leave them.

**Bottom line:** prune unused fixtures in `CitationObjectTest.setUpTestData` and verify the two `TransactionTestCase` classes can downgrade. The tokenizer is already optimal.

---

## Module 8 — `lib` (4.2k lines / 2 files)

`test_helpers.py` defines the **shared mixins inherited suite-wide** — inefficiency
here is a force multiplier paid by every consumer.

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| DB-backed `TestCase` + `fixtures=["test_court.json"]` + 4-object `setUp`, but **every** test calls only pure string functions (the fixture/setUp objects are never used) — paid on ~20 methods | `tests.py:374-692` (`TestModelHelpers`) | Convert to `SimpleTestCase`, drop `fixtures` + `setUp`; build the one `Opinion()` in-memory | S |
| DB `TestCase` + large `court_data.json` fixture but only does `Court.objects.get("akb")` + unsaved `Docket()` | `tests.py:82-109` (`TestPacerUtils`) | Replace fixture with one `CourtFactory(id="akb")` in `setUpTestData` | M |
| **Fat shared mixin** `SearchTestCase` builds ~30 rows for all 5 consumers; `citation_5` is created twice (`:1129` dead/overwritten orphan row) | `test_helpers.py:1008-1216` | Split into lean base (1 docket/cluster/opinion) + opt-in subclasses; fix dead `citation_5` | L (split) / S (citation_5) |
| **Fat shared mixin** `RECAPSearchTestCase` builds a deep parties/attorneys/opinions-cited graph for 4 consumers, many non-ES | `test_helpers.py:1219-1329` | Move opinion+`OpinionsCitedByRECAPDocument` (1276-1287) and second docket/`rd_2` (1299-1328) into opt-in subclass | L |

### Shared-mixin object counts (force multiplier — consumer counts grepped across `cl/`)

| Mixin | Rows in `setUpTestData` | ~Consumers |
|---|---|---|
| `SearchTestCase` | ~30 | 5 |
| `PeopleTestCase` | ~20 | 7 |
| `RECAPSearchTestCase` | ~20 | 4 |
| `CourtTestCase` | 2 (lean — good) | 7 |
| `SimpleUserDataMixin` | 1 | 7 |

### MED / LOW

- `test_helpers.py:862-1005` (`PeopleTestCase`) — 7 consumers; pin Faker-random unset string fields to static values; lean base + rich subclass.
- `test_helpers.py:1432-1532` (`AudioESTestCase`) — loads 3 JSON fixtures **and** builds factory objects (duplicative); drop fixtures (policy).
- `test_helpers.py:1397-1429` (`AudioTestCase.tearDownClass`) — redundant `Audio.objects.all().delete()` under rollback.
- `test_helpers.py:790-837` (`PrayAndPayTestCase`) — 6 `RECAPDocumentFactory` each pull ~4 parent rows (~24 hidden); reduce to RDs actually asserted, share one Docket.
- `tests.py:843-849, 859-865, 1170-1174, 1218` — `print(...)`/`print("✓")` in loops on `SimpleTestCase`; delete, use `subTest()`.

**Bottom line:** the three fat mixins are the highest-leverage target in the whole suite (every consumer pays for rows it may not use), but splitting them is L-effort + per-consumer verification. Quick wins: `TestModelHelpers`→`SimpleTestCase`, dead `citation_5`, `AudioTestCase` teardown, print removal.

---

## Module 9 — `scrapers` (3.5k lines / 2 main files)

Both `time.sleep` refs MOCKED (`tests.py:2625, 2670`). No VCR — uses `responses` with
tiny fixtures (cheap). Main waste: cheap tests hosted in expensive classes, and
fully-mocked tests on DB-backed `TestCase`.

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| Pure-function/no-ES tests live inside `OpinionVersionTest` (`ESIndexTestCase, TransactionTestCase` + 2× `rebuild_index` in setUpClass) → pay full index rebuild for no-DB asserts | `tests.py:1717-1726, 1925, 1956` (`test_docket_source_merging`, `test_string_merging`, `test_transitive_redirection`) | Move them out to a cheap `TestCase`/`SimpleTestCase` | S |
| `setUp` re-opens & re-saves 6 fixture files to storage before **every** test (~36 reads/writes); each test needs one | `tests.py:462-512` (`IngestionTest`) | Load files in `setUpTestData`, or lazily per-test | M |
| Whole class DB-backed `TestCase` but every collaborator is mocked (no DB touched) | `test_tames_poller.py:111` (`TamesPollerTest`) | Change to `SimpleTestCase` | S |
| `ESIndexTestCase, TransactionTestCase` + 2× `rebuild_index`, single test builds ~30 objects | `tests.py:1296-1664` (`OpinionVersionTest`) | Verify `TransactionTestCase` needed (on-commit ES signals in `merge_versions_by_download_url`); if `captureOnCommitCallbacks` works, switch to `TestCase` | M |

### MED / LOW

- `setUp`→`setUpTestData` (read-only, not mutated): `tests.py:992-1045` (`ScraperDocketMatchingTest`), `tests.py:1134-1187` (`UpdateFromTextCommandTest`).
- `tests.py:2259-2347` (`SubscribeToSCOTUSTest`) — 5 pure transcription-cleaning tests pay DB setup for nothing; split into `SimpleTestCase` + merge via `subTest()`.
- `tests.py:2550, 2770` — hoist `User.objects.get("recap-email")` to `setUpTestData`.
- `test_tames_poller.py:285-305` (`SubscribePendingCasesTest`) — tracker in `setUp` → `setUpTestData`.
- `test_tames_poller.py:124,164,193,229,270` — redundant double-patch of `.chain` (setUp + per-test); keep one.

**setUp tally:** ~6 of the file's `setUp` defs are safe `setUpTestData` conversions; 3 are unsafe (per-test mock/state). **Bottom line:** evict cheap tests from `OpinionVersionTest` and flip `TamesPollerTest` to `SimpleTestCase`.

---

## Module 10 — `opinion_page` (3k lines / 1 file)

No `TransactionTestCase` misuse. Page-render tests → template-render + Postgres cost.

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| `setUp` creates 2 dockets + 5 DEs + 6 RDs + court + user on **every** test (5 tests), none mutated; plus manual `tearDown` delete | `tests.py:2264-2361` (`DocketEntryFileDownload`) | Move to `setUpTestData`; delete the manual `tearDown` | M |
| 8 tests each do a full async GET + v2 template render of the **same** docket to assert different substrings | `tests.py:2848-2937` (`DocketEntryRowsV2Test`) | Merge the 7 static-content ones into one render-once `subTest` block (keep empty-state + csv-export separate) → ~7 renders to 1 | M |

### MED / LOW

- `tests.py:177-255` (`OpinionPageLoadTest`) — full ES index build (`ESIndexTestCase` + reindex command) for a **single** direct-cluster-page assertion. Verify the view hits ES; if not, drop `ESIndexTestCase`.
- `tests.py:765-919` (`test_volume_pagination`) — one test creates ~9 citations/clusters/dockets/courts; share courts, `create_batch` where possible.
- `tests.py:1491-1632` (`UploadPublication`) — re-queries `Person.objects.filter` 5× per test → `setUpTestData`; drop `Docket.objects.all().delete()` tearDown (keep only rmtree).
- 4 classes still use Django JSON fixtures (`tests.py:161, 478, 1224, 1279`) — migrate to FactoryBoy (policy + speed, L).
- Sitemap `setUp` bodies (`:1345, 1474`) are pure attr assignment → class attributes.
- `tests.py:2356` (`DocketEntryFileDownload.tearDown`) — `User.objects.all().delete()` could nuke base-class users; remove with the HIGH fix.

**setUp tally:** 4 of 9 are clean conversions (best: `DocketEntryFileDownload`), 3 partial. **Bottom line:** the `DocketEntryFileDownload` conversion + `DocketEntryRowsV2Test` render-once merge are the wins.

---

## Module 11 — `favorites` (1.9k lines / 1 file)

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| 3 selenium tests on `StaticLiveServerTestCase`+`ESIndexTestCase` (browser + live server + per-test ES rebuild); note CRUD already HTTP-covered by `NoteTest` | `tests.py:125-387` (`UserNotesTest`) | Consolidate to **1** JS-only test (Alpine modal save/edit); move persistence asserts to HTTP-client tests. Removes 2 ES/live-server cycles **and all 3 real sleeps** | M |

### MED / LOW

- **3 REAL (unmocked) `time.sleep`:** `tests.py:259` (1s), `:286` (1s), `:373` (0.5s) — all in the selenium tests; replaced for free by the consolidation above (or `WebDriverWait`).
- `tests.py:442-470` (`APITests`) — uses **API v3** (violates "always v4"); manual `tearDown` deletes redundant under rollback. Migrate to v4.
- `tests.py:68-96` (`NoteTest.setUpTestData`) — `docket_2`/`docket_3` (72-73) never referenced; delete.
- `tests.py:804-1020` — 5 `get_top_prayers` ranking tests with heavy `create()` churn; merge via `subTest()` over ranking factor, share `setUpTestData` RDs.
- `tests.py:1073, 1088, 1188` — manual `cache.adelete("prayer-stats-*")` leaks on failure; mock `cache` like the lifetime test does.

### `time.sleep` / `selenium`

- 3 sleeps all **REAL**. Of 3 selenium tests: `test_logged_in_user_can_save_note` and `test_anonymous_user_is_prompted...` largely duplicate HTTP/auth coverage; only `test_user_can_change_notes` (edit modal) is uniquely JS. Consolidate to one.

**Bottom line:** collapsing the 3 selenium tests to 1 kills the only 3 real sleeps in the module + 2 ES/live-server cycles — the biggest favorites win.

---

## Module 12 — `ai` (1.9k lines / 1 file)

**All external calls mocked** — provider is Google Gemini (`genai.Client` patched at
`:111,118,128,…`), boto3 patched, fake env creds, no transformers/torch. Zero network
or model-load risk. No `TransactionTestCase`.

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| 2 `Prompt.objects.create` rows in `setUp` re-inserted for **every** test (~10+12+7 tests), read-only | `tests.py:711-722, 1240-1251, 1781-1791` (`SendGeminiBatchesTest`, `CheckGeminiBatchStatusTest`, `DeduplicationTest`) | Move to `setUpTestData` → removes ~50+ redundant inserts | S |
| `CourtFactory`+`DocketFactory` (heavy Faker graph) in `setUp` for a class with one test | `tests.py:35-37` (`AiModelsTest`) | Move to `setUpTestData` or use `.build()` | S |

### MED / LOW

- `tests.py:1286/1366` (success vs mixed) + error-branch trio — merge via `subTest()` over (payload, expected status); share `_create_task` setup.
- `tests.py:1781-1831` (`DeduplicationTest`) — 5 read-only dedup tests collapsible to one `subTest`; `task.save()` at 1830 is a redundant 2nd write.
- `tests.py:406` — inline `from google.genai.types import JobState` already imported at top.

**Bottom line:** the `Prompt` `setUp`→`setUpTestData` moves are trivial and remove ~50 inserts.

---

## Module 13 — `donate` / `audio` / `stats` (2.7k lines / 3 files)

### donate (all Neon calls mocked, no Stripe path)

- **HIGH** `tests.py:32-51, 917-936` — `setUp` builds `UserProfileWithParentsFactory` (User+Profile+parents) + a redundant 2nd `.save()` for **every** test (~25 in `MembershipWebhookTest`, only `self.data` mutates). Move profile to `setUpTestData`; fold `neon_account_id` into the factory call (kills the extra UPDATE). Biggest win in these three files.
- LOW `tests.py:85` — `create_batch(17)` to test truncation-to-10; 12 suffices.

### audio (OpenAI mocked)

- **HIGH** `tests.py:379-386` — `audio_bigger_than_limit_duration` writes a **26 MB** in-memory `FileField` blob in `setUpTestData`; appears unreferenced by any test method. Verify and delete (or shrink to ~25 MB).
- MED `tests.py:658-891` (`ReenqueueDaemonTest`) — `_build_window_audios` makes a fresh Docket per Audio (4-5/test); reuse one `setUpTestData` docket if the cycle query allows.
- MED `tests.py:557/614` — success vs failure transcription tests mergeable via `subTest`.

### stats

- MED `tests.py:50-55, 189-261, 377-428, 446-528` — pure-logic classes (`MilestoneTests`, `PrometheusMetricsTests`, `CeleryQueueCollectorTests`, `ValidateLabelsTests`, `GetPrometheusKeyTests`) on DB-backed `TestCase` → `SimpleTestCase` (removes per-test txn + Redis teardown round-trip across ~13 methods).
- MED `tests.py:142-152` (`StatTests.setUp`) — scrubs bare `test*` Redis keys (not namespaced) → parallel-worker collision risk; namespace the test stat names or assert on deltas.
- LOW `tests.py:12` — dead `django.test.TestCase` import shadowed by the CL one; `tests.py:153-167` — 3 tiny tally tests mergeable via `subTest`.

---

## Module 14 — small apps (`simple_pages`, `custom_filters`, `visualizations`, `disclosures`, `oauth`, `people_db`)

### HIGH impact

| Finding | Location | Fix | Effort |
|---|---|---|---|
| `TransactionTestCase` for a test that just creates one person+position and counts (no txn-boundary behavior) | `people_db/tests.py:8` (`TestPersonWithChildrenFactory`) | Change to `TestCase` | S |
| Selenium `test_disclosure_homepage` is a strict subset of `test_disclosure_search` (same nav + search-bar assertions) | `disclosures/tests.py:293` | Delete it (covered by search); or move the page-load check to a non-selenium view test | M |

### MED / LOW

- `disclosures/tests.py:116-166` (`DisclosureAPITest.setUpTestData`) — ~60 rows (`create_batch(10,...)` for debts/spousal/gifts/reimb) but those filter tests only assert count==1; trim batches where 10 isn't load-bearing (investments batch of 10 is).
- `visualizations/tests.py:236-239` (`APIVisualizationTestCase.tearDown`) — redundant `SCOTUSMap.objects.all().delete()` under rollback; remove.
- `disclosures/tests.py:90` (`test_extraction_and_ingestion_jef`) — calls **real** `microservice("extract-disclosure")` over the network (slow/flaky); out of scope but flag.
- `oauth/tests.py:75-137` — ~6 validation-reject DCR tests fail before any DB write but run on `APITestCase`; possible `SimpleTestCase` (LOW confidence — view may touch DB middleware, verify). Also inline imports at 290-298 (policy).
- `people_db/tests.py:25-59` (`PersonPageSearchButtons`) — two tests issue the identical `view_person` GET; merge to one fetch-once test.
- **`custom_filters/tests.py` is the model to follow** — all classes already `SimpleTestCase` (pure logic). No DB findings.
- `simple_pages` — well-structured; page-load loops already batched via `subTest`, genuinely DB-backed.

---

## Module 15 — shared test infra `cl/tests/` (suite-wide force multipliers)

### HIGH impact — the single biggest suite-wide win

| Finding | Location | Fix | Effort |
|---|---|---|---|
| **`BaseSeleniumTest.setUp` unconditionally rebuilds the audio ES index + delete/recreate OpinionCluster index + runs the full `cl_index_parent_and_child_docs` opinion reindex command on EVERY selenium test method** (~29 methods across 7 classes), regardless of relevance | `base.py:68-74` | Gate behind a class flag (e.g. `rebuild_search_indexes = False`); only `OpinionSearchFunctionalTest`, the audio-touching issue412/feeds tests opt in. **Proof it's safe:** `LiveUserTest` & `DisclosurePageTest` already skip `super().setUp()` and pass | M |
| 4 of 7 `test_feeds.py` tests use feedparser against the live server (no browser) and duplicate non-selenium `OpinionFeedTest` coverage | `test_feeds.py:21, 77-130` | Move the 4 feedparser-only methods to a plain `LiveServerTestCase`/`TestCase`; keep only the 3 truly browser-driven on selenium | M |
| `providers.py:citation()` rebuilds a filtered list over **all of `REPORTERS`** (large reporters_db dict) on **every** `.citation()` call — runs for every citation generated suite-wide | `providers.py:85-104` | Hoist the static filtered list to a module-level constant computed once at import | S |

**Classes inheriting `BaseSeleniumTest` (7):** `FeedsFunctionalTest`, the 3 `issue412` Blocked tests, `OpinionSearchFunctionalTest`, `AlertSeleniumTest`, `UserNotesTest`, `LiveUserTest`*, `DisclosurePageTest`* (*already skip the ES rebuild and pass — proof most don't need it).

### MED / LOW

- `base.py:182-191` (`_update_index`) — uses the heavyweight management command per test rather than the registry `rebuild_index` path; swap where the command's parent/child behavior isn't under test (verify equivalence).
- `test_issue412.py:36-167` — Opinion/Docket "Blocked" badge tests mostly re-test template rendering + auth (not JS) → demote to request-level `TestCase` HTML assertions (verify badge isn't JS-gated). All 3 issue412 classes also use Django JSON fixtures (policy).
- `fakes.py:222-238, 368-390` and `utils.py:156-303` — `.data`/`_parse_text` properties rebuild FactoryBoy/Faker objects on **every access**; cache if read in loops (verify call frequency).
- `fakes.py` confirmed correct — stand-ins that prevent real PACER/network calls. No I/O issues in `utils.py`.

---

## Cross-cutting themes & prioritized quick wins

The same patterns recur across modules. Ranked by **effort-adjusted payoff**:

### Tier 1 — high payoff, low/medium risk (do first)

1. **Selenium ES rebuild → opt-in** (`base.py:68-74`). Suite-wide multiplier: ~29 selenium methods each currently pay an audio reindex + opinion reindex command. Biggest single lever. *(M)*
2. **`setUp` → `setUpTestData`** for read-only shared rows. Recurs everywhere; biggest concentrations: `recap` (`RecapPdfFetchApiTest`, `RecapAttPageFetchApiTest`, `RecapEmailDocketAlerts`), `donate` (`MembershipWebhookTest`, ~25 tests), `ai` (`Prompt` rows ×3 classes), `opinion_page` (`DocketEntryFileDownload`), `corpus_importer` (`PacerDocketParserTest`). *(S–M each)*
3. **Pure-logic tests on DB-backed `TestCase` → `SimpleTestCase`.** `lib` (`TestModelHelpers`), `search` (`TestCleanDocketNumberRaw`, 3 semantic form classes), `stats` (5 classes), `scrapers` (`TamesPollerTest` + transcription tests), `api` (`ReplicaRoutingMiddlewareTest`). Removes txn setup + Redis teardown per test. *(S each)*
4. **`TransactionTestCase` → `TestCase`** where no commit-boundary behavior is tested: `users` (`UserTest`, `UserDataTest` via `LiveServerTestCase`), `people_db` (`TestPersonWithChildrenFactory`). Verify `captureOnCommitCallbacks` covers ES-signal classes (`search`, `citations`, `scrapers`, `alerts`). *(S–M)*
5. **Delete dead/redundant code:** `import_columbia/html_test.py` (dead script), debug `print()`s (`recap`, `lib`, `corpus_importer`, `test_feeds`), duplicate `rebuild_index` calls, the 26 MB audio blob, `add_bcc_random` 2M-iteration loop, duplicate imports. *(S)*
6. **`providers.py:citation()`** REPORTERS filter → module constant. *(S)*

### Tier 2 — high payoff, higher effort

7. **Per-test ES/percolator index recreation → class-scoped + per-test doc clear:** `alerts` (`tests_recap_alerts.py:2797`, `tests_opinion_alerts.py:148`, `tests.py:4258`), plus `rebuild_index`-then-empty antipatterns (`search` person/opinion command tests). *(M)*
8. **Split the fat shared mixins** (`lib/test_helpers.py`: `SearchTestCase`, `RECAPSearchTestCase`, `PeopleTestCase`) into lean base + opt-in subclasses. Highest theoretical leverage (paid by 4-7 consumers each) but needs per-consumer verification. *(L)*
9. **Merge single-assertion test families via `subTest()`:** `search` (~27 recap filter tests, run 2× via V3/V4), `api` (~40 pagination endpoint tests), `recap`/`alerts`/`ai`/`favorites` duplicate-corpus pairs. Changes failure granularity — confirm team accepts. *(M)*
10. **Migrate Django JSON fixtures → FactoryBoy** (`api`, `opinion_page`, `lib`, `test_feeds`, `issue412`) — policy compliance + avoids per-class fixture deserialization. *(L)*

### Correctness bugs found along the way (fix regardless of perf)

- `search/tests_es_recap.py:3668` — shared `cls.test_cases` dict mutated in place.
- `search/tests_es_oral_arguments.py:1490` — test builds params but never issues the request (case silently untested).
- `recap/test_recap_email.py:83-102, 2744` — shared dict mutation (shallow copy of nested data) leaks across tests.
- `api/tests.py:3095` — asserts on wrong variable (`webhook_event.response` vs `_2`/`_3`).
- `favorites/tests.py:442` — uses deprecated API **v3** (should be v4).

### Verified NON-issues (don't waste effort)

- eyecite tokenizer (`citations`) is already a cached module-level singleton — the profile cost is one-time, not per-test.
- All `time.sleep` in `corpus_importer` (16) and `search/test_pacer_bulk_fetch` (4) are mocked. Only **`favorites`** has 3 real sleeps (in selenium, removed by consolidation).
- All external API calls mocked: `ai` (Gemini), `audio` (OpenAI), `donate` (Neon). No network in those paths.
- `custom_filters` and `simple_pages` are already well-structured — leave them.

---

# PART 2 — MEASURED TIMINGS (real numbers via `manage.py test --durations 0 --timing --keepdb --parallel 1`, Django 6.0)

**Measurement lesson (applies to all modules):** `--durations` times only the test
*method body*, NOT `setUp`/`setUpClass`/teardown. In `users` the 120 method bodies
summed to ~3s while the module took **84s** — ~80s hidden in fixtures/transaction
machinery. So per-test durations are nearly useless for this suite; **class-level
totals** (run each `TestClass` separately) are what reveal the real cost. Numbers
below are class-level wall-clock.

## `users` — measured

Module: **120 tests in 84.1s**. Three classes dominate (**65s = 77%**):

| Class | Base | Tests | Total | Per-test | Verdict vs static finding |
|---|---|---|---|---|---|
| `UserTest` | `LiveServerTestCase` (=TransactionTestCase) | 5 | **26.0s** | ~5.2s | ✅ CONFIRMED HIGH — async-HTTP tests, no live server needed. Convert to `TestCase`. |
| `UserDataTest` | `LiveServerTestCase` | 5 | **26.5s** | ~5.3s | ✅ CONFIRMED HIGH — same. |
| `LiveUserTest` | `BaseSeleniumTest` | 2 | **12.5s** | ~6.3s | ✅ CONFIRMED HIGH — 2 no-JS password tests = 12.5s of browser boot. |
| `CustomBackendEmailTest` | `TestCase` | 23 | 0.9s | ~0.04s | ❌ REFUTED — `test_add_bcc_random` (2M-iter loop) = 0.629s, slowest *method* in module but sub-second. Whole class 0.9s. Drop to LOW. |
| `ViewApiUsageTest` | `TestCase` | 6 | 0.8s | — | fast, fine |
| `EmailBrokenTest` | `TestCase` | 5 | 1.7s | — | modest |

**Measured takeaway:** converting `UserTest`+`UserDataTest` off `LiveServerTestCase`
→ `TestCase` should reclaim **~45-50s** (the ~5s/test truncation tax → <1s like the
other HTTP classes). Deleting/rewriting the 2 selenium password tests reclaims
**~12s**. Together ≈ **70% of the users module's runtime**, all from 12 tests.
The `add_bcc_random` optimization is NOT worth doing.

## Small/medium modules — measured (batch)

| Module | Tests | Total | Verdict |
|---|---|---|---|
| `oauth` | 22 | **0.16s** | Already trivial — SimpleTestCase suggestion = noise. SKIP. |
| `donate` | 29 | **0.46s** | ❌ REFUTES HIGH claim — `MembershipWebhookTest` setUp→setUpTestData saves <0.5s. Drop to LOW. |
| `ai` | 54 | **0.54s** | ❌ REFUTES HIGH claim — `Prompt` setUp moves (~50 inserts) save <0.5s. Drop to LOW. |
| `visualizations` | 12 | **0.60s** | ❌ "heavy graph" fixture is 0.6s total. LOW. |
| `simple_pages` | 25 | 1.35s | ✅ already well-structured (as stated). |
| `audio` | 15 | 2.2s | 26MB blob worth removing for memory/correctness but NOT a timing win. Re-rank LOW. |
| `stats` | 31 | 3.5s | SimpleTestCase reclassification saves ~1-2s. LOW absolute. |
| `people_db` | 3 | 5.2s | see below — TransactionTestCase confirmed. |
| `disclosures` | 15 | 17.9s | see below — selenium confirmed. |

### Class-level attribution (the two that matter)

| Class | Base | Tests | Total | Verdict |
|---|---|---|---|---|
| `disclosures…DisclosurePageTest` | selenium | 2 | **15.7s** | ✅ CONFIRMED — 87% of the disclosures module is this one selenium class. `test_disclosure_homepage` is redundant w/ `test_disclosure_search`; demote both off selenium → reclaim ~15s. |
| `disclosures…DisclosureAPITest` | `TestCase` | 11 | **0.3s** | ❌ REFUTES MED — the ~60-row `setUpTestData` costs nothing. SKIP trimming. |
| `disclosures…DisclosureIngestionTest` | `TestCase` | 2 | 1.8s | real network microservice call; out of scope. |
| `people_db…TestPersonWithChildrenFactory` | **TransactionTestCase** | 1 | **5.0s** | ✅ CONFIRMED HIGH — 5.0s for ONE trivial create-and-count test. → `TestCase` should drop it to <0.1s. |
| `people_db…PersonPageSearchButtons` | `TestCase` | 2 | 0.23s | merge-to-one-fetch saves ~0.1s. LOW. |

## ⚑ Re-ranking conclusion (measured)

The static audit's per-module micro-optimizations (`setUp`→`setUpTestData` for small
graphs, `SimpleTestCase` reclassification, trimming modest fixtures) are **directionally
correct but have negligible absolute payoff** — every ordinary `TestCase` test runs in
**0.01-0.3s**. The measured cost is dominated by **base-class choice**, not factory churn:

- **Selenium test** ≈ **6-8s/test** (browser boot, in `setUpClass`) — invisible to `--durations`.
- **`TransactionTestCase`/`LiveServerTestCase` test** ≈ **5s/test** (full-schema table truncation, no rollback).
- **(pending) ES `rebuild_index`** in search/recap/alerts.

**Revised strategy:** ignore the long tail of small-module tweaks. Pursue only:
(1) eliminate/convert `TransactionTestCase` & `LiveServerTestCase` misuse,
(2) eliminate/consolidate selenium + make `BaseSeleniumTest`'s ES setup opt-in,
(3) reduce ES `rebuild_index` frequency in the big-3 ES modules.

## Suspect-class measurements across heavy modules (class-level wall-clock)

Sorted by total time. **The single variable that predicts cost is the base class.**

| Class | Base class | Tests | Total | Per-test | Verdict |
|---|---|---|---|---|---|
| `search…OpinionSearchFunctionalTest` | **selenium** | 6 | **52.5s** | 8.7s | ✅ HIGH — browser + per-test ES reindex (`super().setUp()`). |
| `search…EsOpinionsIndexingTest` | **TransactionTestCase** | 9 | **51.8s** | 5.8s | ✅ HIGH — biggest indexing class. |
| `scrapers…OpinionVersionTest` | **TransactionTestCase** | 9 | **49.9s** | 5.5s | ✅ HIGH — also hosts cheap pure-fn tests paying this tax. |
| `search…PeopleIndexingTest` | **TransactionTestCase** | 5 | **30.4s** | 6.1s | ✅ HIGH. |
| `users…UserDataTest` | **LiveServerTestCase** | 5 | 26.5s | 5.3s | ✅ HIGH (PART 2). |
| `users…UserTest` | **LiveServerTestCase** | 5 | 26.0s | 5.2s | ✅ HIGH (PART 2). |
| `citations…UnmatchedCitationTest` | **TransactionTestCase** | 4 | **20.5s** | 5.1s | ✅ HIGH — does almost nothing, pays 5s/test anyway. |
| `disclosures…DisclosurePageTest` | **selenium** | 2 | 15.7s | 7.9s | ✅ HIGH (PART 2). |
| `citations…ReindexESCiteFieldsTest` | **TransactionTestCase** | 2 | **12.7s** | 6.4s | ✅ HIGH. |
| `search…OralArgumentIndexingTest` | **TransactionTestCase** | 2 | 12.6s | 6.3s | ✅ HIGH. |
| `users…LiveUserTest` | **selenium** | 2 | 12.5s | 6.3s | ✅ HIGH (PART 2). |
| `alerts…RECAPAlertsPercolatorTest` | TestCase + per-test percolator index reset | 16 | 10.5s | 0.66s | ✅ MED — per-test `_index.delete()+init()`. |
| `search…RECAPSearchTest` | ESIndexTestCase+TestCase | 47 | 10.4s | 0.22s | ◐ MED — 27 filter tests; subTest merge saves ~5s. |
| `alerts…OpinionAlertsPercolatorTest` | TestCase + per-test percolator reset | 9 | 9.7s | 1.08s | ✅ MED. |
| `alerts…AlertSeleniumTest` | **selenium** | 1 | 8.2s | 8.2s | ✅ HIGH — 1 test, 8.2s; → async test. |
| `citations…CitationObjectTest` | ESIndexTestCase+TestCase | 14 | 4.7s | 0.33s | ◐ LOW-MED — fixture pruning saves little (downgraded). |
| `search…SweepIndexerCommandTest` | ESIndexTestCase+TestCase | 3 | 4.6s | — | modest. |
| `corpus_importer…PacerDocketParserTest` | TestCase | 3 | 0.83s (3.7s w/setup) | — | ◐ modest (downgraded). |
| `scrapers…IngestionTest` | TestCase | 7 | 2.1s | 0.3s | ◐ LOW-MED — per-test file reads (downgraded). |
| `search…IndexJudgesPositionsCommandTest` | ESIndexTestCase+TestCase | 1 | 2.1s | — | modest. |
| `alerts…SearchAlertsIndexingCommandTests` | ESIndexTestCase+TestCase | 3 | 2.1s | — | modest. |
| `opinion_page…OpinionPageLoadTest` | ESIndexTestCase | 1 | 2.0s | — | modest (1 test). |
| `api…V4DRFPaginationTest` | TestCase | 47 | **1.7s** | 0.036s | ❌ REFUTED HIGH — merging 40 tests saves ~1s. Drop. |
| `opinion_page…DocketEntryRowsV2Test` | TestCase | 10 | 0.95s | — | ❌ render-merge saves ~0.5s. LOW. |
| `corpus_importer…PacerDocketParserTest` | (see above) | | | | |
| `recap…RecapEmailDocketAlerts` | TestCase | 30 | **0.27s** | 0.009s | ❌ REFUTED HIGH — ~130 "redundant" writes = 0.27s total. Drop. |
| `opinion_page…DocketEntryFileDownload` | TestCase | 4 | **0.57s** | — | ❌ REFUTED HIGH — setUp→setUpTestData saves <0.5s. Drop. |
| `recap…RecapAttPageFetchApiTest` | TestCase | 5 | 0.17s | — | ❌ REFUTED HIGH. |
| `recap…RecapPdfFetchApiTest` | TestCase | 7 | **0.07s** | 0.01s | ❌ REFUTED HIGH — the flagged per-test rebuild = 0.07s. Drop. |
| `scrapers…TamesPollerTest` | TestCase | 4 | 0.02s | — | ❌ REFUTED — already 0.02s; SimpleTestCase saves nothing. |

### ⚑ Definitive measured conclusion

**~14 classes (~50 test methods) account for ~365 seconds.** The other ~thousands of
tests run in fractions of a second each. The cost is **base-class-bound**, not
fixture-bound:

- **`TransactionTestCase` ≈ a fixed ~5-6s/test table-truncation tax** (CourtListener's
  large schema is flushed after every test; no transaction rollback). It dominates
  even when the test body does nothing (`UnmatchedCitationTest`: 5.1s/test).
- **Selenium ≈ 6-9s/test** (browser boot + the unconditional `BaseSeleniumTest` ES rebuild).
- Per-class ES `rebuild_index` in `setUpTestData` is **cheap and amortized** (ES `TestCase`
  classes run 0.2-0.33s/test). Per-**test** ES/percolator resets (alerts) are the only
  ES item worth fixing.

**The entire long tail of `setUp`→`setUpTestData` / `SimpleTestCase` / fixture-trim
findings in PART 1 is REFUTED as wall-clock-relevant** — those modules already run in
<3s. Pursuing them is churn for ~0s gain (still valid as code-cleanliness, not perf).

### Revised, measured action plan (do ONLY these for speed)

1. **Convert `TransactionTestCase` → `TestCase` + `captureOnCommitCallbacks`** where ES
   on-commit signals permit (verify each): `search.EsOpinionsIndexingTest` (~52s),
   `scrapers.OpinionVersionTest` (~50s), `search.PeopleIndexingTest` (~30s),
   `citations.UnmatchedCitationTest` (~20s), `citations.ReindexESCiteFieldsTest` (~13s),
   `search.OralArgumentIndexingTest` (~13s), `people_db.TestPersonWithChildrenFactory` (~5s).
   **Potential: ~150-180s** (each test drops from ~5-6s to <0.5s). Highest leverage by far.
2. **Convert `users.UserTest`/`UserDataTest` off `LiveServerTestCase` → `TestCase`** (~45-50s).
3. **Selenium: make `BaseSeleniumTest` ES rebuild opt-in + consolidate/convert** the no-JS
   selenium tests (`search.OpinionSearchFunctionalTest` ~52s, `users.LiveUserTest` ~12s,
   `disclosures.DisclosurePageTest` ~16s, `alerts.AlertSeleniumTest` ~8s, plus favorites).
   **Potential: ~80-100s.**
4. **alerts percolator: per-test index reset → setUpClass + per-test doc clear** (~10s).
5. (optional) merge `search.RECAPSearchTest` 27 filter tests via subTest (~5s).

**Estimated total reclaimable: ~300s+ of serial time, from ~15 classes.** Everything
else in PART 1 can be skipped for performance purposes.

## `lib` — measured

Module: **93 tests in 1.0s**. ❌ REFUTES the `TestModelHelpers`→`SimpleTestCase` and
"fat shared mixin" HIGH/L claims as *perf* items — the whole module is 1s, and the fat
mixins' cost is amortized once-per-class in consumers' `setUpTestData` (measured cheap:
ES `TestCase` consumers run 0.2-0.33s/test). Mixin splits remain valid as cleanliness,
not speed.

---

# Measurement phase — COMPLETE

Coverage: full-module runs for `users, lib, custom_filters` + 9 small modules; class-level
attribution for 25 suspect classes across `search, recap, alerts, citations, api,
opinion_page, scrapers, corpus_importer, disclosures, people_db`. Raw logs in
`.test_timings/` (untracked).

**One-line takeaway:** test-suite time is concentrated in **~15 `TransactionTestCase` /
`LiveServerTestCase` / selenium classes (~365s)**; the rest of the suite is already fast,
and the PART 1 micro-optimizations are not worth pursuing for speed. Execute the
"Revised, measured action plan" above.

---

# PART 3 — `captureOnCommitCallbacks` conversion: VALIDATED (proof-of-concept)

**Hypothesis:** the heavy `TransactionTestCase` ES classes can become `TestCase` +
`captureOnCommitCallbacks(execute=True)`, removing the ~5s/test table-truncation tax
while preserving behavior — *because* CL's ES indexing is gated on
`transaction.on_commit(...)` (verified: `cl/lib/es_signal_processor.py` uses it ~25×).

**PoC target:** `search…OralArgumentIndexingTest` (`tests_es_oral_arguments.py:2887`) —
the canonical OA ES-indexing-on-commit pattern, 2 tests.

**Result (measured, `--keepdb --parallel 1`, same machine state):**

| | Base class | Tests | Wall-clock | Per-test | Outcome |
|---|---|---|---|---|---|
| BEFORE | `TransactionTestCase` | 2 | **12.43s** | ~6.2s | OK |
| AFTER | `TestCase` + `captureOnCommitCallbacks` | 2 | **2.14s** | ~1.07s | OK ✅ |

**~5.8× faster; ~10.3s reclaimed on 2 tests.** All assertions pass, including the
exact ES task-count checks (`reset_and_assert_task_count`) — the hardest part to
preserve. The residual ~1s/test is the real ES indexing work itself (now the floor).

### Conversion mechanics (the transferable recipe)

1. Base class `TransactionTestCase` → `TestCase` (ruff then auto-removes the now-unused
   import — confirms it was the file's only `TransactionTestCase` user).
2. Wrap every **index-triggering** op (`*.create()`, `.save()`, `.delete()`,
   `m2m.add()`) in `with self.captureOnCommitCallbacks(execute=True):` so the on-commit
   indexing fires before the following ES assertion.
3. For **task-count** tests that `mock.patch` the `.si` signature: the on-commit lambda
   calls `.si()` at *commit* time, so the capture must sit **inside** the mock —
   `with (mock.patch(...), self.captureOnCommitCallbacks(execute=True)):` (context
   managers exit inner-first, so `.si` is invoked while the mock is still active and is
   counted). `expected=0` blocks (no field change / processing-incomplete) register no
   callback, so they need no wrapping.
4. `delete()` paths that use `.delay()` directly (not `on_commit`) don't strictly need
   wrapping, but wrapping is harmless.

### Extrapolation to the other `TransactionTestCase` classes (est. at ~1s/test floor)

| Class | Now | Tests | Est. after | Est. saved |
|---|---|---|---|---|
| `search.EsOpinionsIndexingTest` | 51.8s | 9 | ~9s | ~43s |
| `scrapers.OpinionVersionTest` | 49.9s | 9 | ~9s | ~41s |
| `search.PeopleIndexingTest` | 30.4s | 5 | ~5s | ~25s |
| `citations.UnmatchedCitationTest` | 20.5s | 4 | ~4s | ~16s |
| `citations.ReindexESCiteFieldsTest` | 12.7s | 2 | ~2s | ~11s |
| `search.OralArgumentIndexingTest` | 12.4s | 2 | **2.1s (done)** | **10.3s ✅** |
| `people_db.TestPersonWithChildrenFactory` | 5.0s | 1 | ~0.5s | ~4.5s (likely needs NO capture — no ES) |

**Projected total from the 7 `TransactionTestCase` conversions: ~150s.** Per-test cost
collapses from ~5-6s to ~1s. The PoC confirms the mechanism is sound; each remaining
class needs the same per-op wrapping, verified individually (esp. the task-count and
`UnmatchedCitationTest` post_save-signal assertions).

**Status:** the `OralArgumentIndexingTest` conversion is applied in the working tree
(passing, ruff-clean) but **not committed**.

---

# PART 4 — All 7 `TransactionTestCase`/`LiveServer` ES conversions APPLIED & VERIFIED

Every conversion below is applied in the working tree, passes (`--keepdb --parallel 1`),
is ruff-clean, and was verified to change **no assertion or expected value** (mechanical
diff sweep: only base-class swap + `captureOnCommitCallbacks` wrappers / `use_streaming_bulk`).

| Class | File | Tests | Before | After | Pattern |
|---|---|---|---|---|---|
| `OralArgumentIndexingTest` | search/tests_es_oral_arguments.py | 2 | 12.4s | **2.1s** | capture-wrap (incl. nested-in-mock) |
| `EsOpinionsIndexingTest` | search/tests_es_opinion.py | 9 | 51.8s | **4.7s** | capture-wrap ×41 (6 nested-in-mock) |
| `PeopleIndexingTest` | search/tests_es_person.py | 5 | 30.4s | **4.5s** | capture-wrap ×43 (incl. setUp) |
| `OpinionVersionTest` | scrapers/tests.py | 9 | 49.9s | **3.5s** | capture-wrap ×2 (8 tests were pure-logic, paying the tax for nothing) |
| `UnmatchedCitationTest` | citations/tests.py | 4 | 20.5s | **0.2s** | plain swap — signal is synchronous, no ES; `setUpClass`→`setUpTestData` |
| `ReindexESCiteFieldsTest` | citations/tests.py | 2 | 12.7s | **2.0s** | `use_streaming_bulk=True` on direct `index_parent_and_child_docs` (parallel_bulk is TestCase-incompatible) |
| `TestPersonWithChildrenFactory` | people_db/tests.py | 1 | 5.0s | **0.01s** | plain swap — gratuitous `TransactionTestCase`, no ES |
| **TOTAL** | | **32** | **~183s** | **~17s** | **~166s reclaimed** |

Combined single invocation of all 7 classes: **32 tests in 14.8s** (was ~183s).
Sibling-regression checks passed: full `citations` (69 tests OK), full `people_db` (3 OK).

### Three conversion patterns (decision guide for any remaining `TransactionTestCase`)

1. **Signal-driven ES indexing** (most ES classes): wrap each index-triggering op
   (`create`/`save`/`delete`/m2m `add`) in `with self.captureOnCommitCallbacks(execute=True):`;
   assertions stay outside. For exact-task-count tests, nest the capture **inside** the
   `mock.patch(...)` so the mocked `.si` (called in the on-commit lambda) is still counted.
2. **Explicit indexing** via `index_parent_and_child_docs(...)`: add `use_streaming_bulk=True`
   (its default `parallel_bulk` can't see uncommitted data from worker threads under `TestCase`).
3. **No ES / synchronous signal / gratuitous `TransactionTestCase`**: just swap the base
   class (and prefer `setUpTestData` over a fragile `setUpClass`); no capture needed.

The `TransactionTestCase`/`LiveServerTestCase` import is auto-removed by ruff once a file's
last user is converted. **Status:** applied, not committed.

---

# PART 5 — `LiveServerTestCase` conversion (users) APPLIED & VERIFIED

`LiveServerTestCase` subclasses `TransactionTestCase` AND spins a live server thread,
yet `UserTest`/`UserDataTest` only use `self.async_client` (no browser). Converted both
to `TestCase`; the 4 `self.live_server_url` URL-prefixes were dropped (the test client
takes a path and ignores host — the assertions check `?next=`/`email` sanitization, not
host).

| Class | Tests | Before | After |
|---|---|---|---|
| `users.UserTest` + `users.UserDataTest` | 10 | ~52.5s | **0.48s** |

Full `users` module regression: **84.1s → 18.0s** (120 tests, OK). ruff removed the
now-unused `LiveServerTestCase` import. Assertion-safety sweep: no assertion/expected
value changed — only the base-class swap and host-prefix removal.

Remaining selenium tier (not yet done): `BaseSeleniumTest` ES-rebuild opt-in (suite-wide,
~affects 29 selenium tests) and consolidating no-JS selenium tests
(`search.OpinionSearchFunctionalTest` ~52s, `disclosures.DisclosurePageTest` ~16s,
`users.LiveUserTest` ~12s, `alerts.AlertSeleniumTest` ~8s, `favorites.UserNotesTest`).
These involve coverage judgment (does an HTTP test already cover it?) and need browser-based
verification — recommend doing them with explicit review rather than mechanically.

---

# PART 6 — Selenium tier: `BaseSeleniumTest` ES-rebuild opt-out (implemented, but measured LOW value)

Implemented `BaseSeleniumTest.rebuild_search_indexes` (default **True**, fully
behavior-preserving) so selenium classes that don't query opinion/audio search can skip
the per-test reindex (`cl/tests/base.py`). Opted out `AlertSeleniumTest` (verified OK).

**Measured reality — this lever is small:**
- `AlertSeleniumTest`: 8.2s → 8.2s (test body 8.198s → 7.642s, i.e. **~0.5s saved**). The
  per-test reindex is cheap when the class has little data; the cost is **browser boot**
  (`setUpClass`, once per class) which the flag can't touch.
- `LiveUserTest` and `DisclosurePageTest` **already skip the rebuild** — their `setUp`
  overrides don't call `super().setUp()` (a latent bug: they also skip `reset_browser()`
  cookie-clearing). So the flag does nothing for them; their cost is pure browser boot.
- The classes that pay a *large* reindex (`OpinionSearchFunctionalTest` ~52s/6 tests,
  `FeedsFunctionalTest`, the audio `issue412` tests) genuinely **need** the index — can't opt out.
- `UserNotesTest` (multi-test) likely needs the opinion index (its flow searches then opens
  an opinion) — left at default True, unverified.

**Conclusion:** the earlier assumption that the per-test ES rebuild was a selenium
"force multiplier" is **not supported by measurement**. Selenium cost ≈ browser boot
(~5-8s/class, once) + the real search reindex where it's actually needed. The only
material selenium lever is **reducing the number of selenium tests/classes** — i.e.
converting genuinely no-JS selenium tests to fast HTTP-client tests, or deleting selenium
tests whose coverage is already provided by HTTP tests. That is **coverage-judgment work**
(does an existing HTTP test truly cover it?) and should be done with explicit review, not
mechanically. Candidates (from PART 1): `users.LiveUserTest` (2 no-JS password-reset
tests, ~12s — fully reproducible via `async_client`), `disclosures.DisclosurePageTest`
(`test_disclosure_homepage` is a subset of `test_disclosure_search`), the `issue412`
Opinion/Docket blocked-badge tests (template+auth, likely not JS-gated).

The `base.py` flag + `AlertSeleniumTest` opt-out are harmless and correct, but reclaim
~0s in practice — keep or drop at your discretion.

---

# PART 7 — CONSOLIDATED IMPACT (the full measured effect)

All numbers from the real Django runner (`--keepdb --parallel 1`, Django 6.0), same machine.

## Per-class before → after (the changes that actually moved the needle)

| Module | Class | Tests | Before | After | Saved |
|---|---|---|---|---|---|
| search | `EsOpinionsIndexingTest` | 9 | 51.8s | 4.7s | 47.1s |
| scrapers | `OpinionVersionTest` | 9 | 49.9s | 3.5s | 46.4s |
| search | `PeopleIndexingTest` | 5 | 30.4s | 4.5s | 25.9s |
| users | `UserTest`+`UserDataTest` | 10 | 52.5s | 0.5s | 52.0s |
| citations | `UnmatchedCitationTest` | 4 | 20.5s | 0.2s | 20.3s |
| citations | `ReindexESCiteFieldsTest` | 2 | 12.7s | 2.0s | 10.7s |
| search | `OralArgumentIndexingTest` | 2 | 12.4s | 2.1s | 10.3s |
| people_db | `TestPersonWithChildrenFactory` | 1 | 5.0s | 0.01s | 5.0s |
| **TOTAL** | **8 classes** | **42** | **~235s** | **~17s** | **~218s** |

Combined single run of all 42 tests: **14.9s** (vs ~235s). **~93% faster** on the
optimized classes; **~218s of serial test time reclaimed.**

## Module-level confirmation (full module, before → after)

| Module | Before | After | Notes |
|---|---|---|---|
| `users` | 84.1s | **18.0s** | 120 tests, all pass |
| `people_db` | 5.2s | **0.26s** | 3 tests, all pass |
| `citations` | — | 23.2s (after) | 69 tests pass; class deltas above |

## What did the work

- **`TransactionTestCase` → `TestCase` + `captureOnCommitCallbacks`** (or `use_streaming_bulk`
  for direct `index_parent_and_child_docs`): the ~5-6s/test full-schema truncation tax is
  the dominant suite cost; removing it is where ~all the savings came from.
- **`LiveServerTestCase` → `TestCase`** for async-HTTP tests (users).
- Verified: **no assertions or expected values changed** in any conversion.

## NOT pursued (measured low/zero value — deliberately skipped)

- The entire PART 1 long tail of `setUp`→`setUpTestData` / `SimpleTestCase` / fixture-trim
  ideas in the small modules (donate, ai, audio, oauth, visualizations, stats, lib,
  opinion_page, recap, api): those modules already run in <3s each; the changes reclaim ~0s.
- Selenium ES-rebuild opt-out (PART 6): browser boot dominates, not the reindex → ~0s.

## Remaining non-selenium opportunity (NOT yet applied)

- **alerts percolator per-test index reset** (`RECAPAlertsPercolatorTest` ~10.5s/16 tests,
  `OpinionAlertsPercolatorTest` ~9.7s/9 tests): `setUp` does a full percolator index
  `delete()+init()` every test. Moving index creation to `setUpClass` + a per-test
  delete-by-query doc-clear should reclaim a chunk of the ~20s. This is the last material
  non-selenium lever; ~estimate 10-15s.

---

# PART 8 — Percolator attempt (REVERTED) + last TransactionTestCase + new-improvement hunt

## alerts percolator: APPLIED (initial "counterproductive" reading was a contention artifact)

Moved the per-test `*Percolator._index.delete()+init()` to a once-per-class `setUpClass`
create + per-test `search().query("match_all").delete()` doc-clear (with `tearDownClass`
cleanup).

A first measurement showed it *slower* (9.7s → 18.0s) and it was reverted — but that run
was contended by a concurrent full-suite run. **Re-measured under quiet conditions** (each
value stable across two back-to-back runs):

| Class | Tests | Before | After | Saved |
|---|---|---|---|---|
| `OpinionAlertsPercolatorTest` | 9 | 8.93s | **7.49s** | ~1.4s |
| `RECAPAlertsPercolatorTest` | 16 | 9.30s | **6.78s** | ~2.5s |
| **Total** | 25 | 18.2s | **14.3s** | **~3.9s** |

Both pass; no assertions changed; ruff-clean. **Kept.** Lesson: validate perf numbers under
quiet conditions — a concurrent suite run inflated the original "after" by ~2×.

## `search.LLMCleanDocketNumberTests`: TransactionTestCase → TestCase (the last one)

The final `TransactionTestCase` in the codebase. Runs a daemon command (eager Celery)
that dispatches work via `transaction.on_commit`, so the `call_command(...)` needed
wrapping in `captureOnCommitCallbacks(execute=True)` (nested inside the existing
`mock.patch`).

| | Before | After |
|---|---|---|
| `LLMCleanDocketNumberTests` | 5.26s | **0.19s** |

Verified: no assertions changed. **There are now zero `TransactionTestCase` and zero
non-selenium `LiveServerTestCase` classes left in the codebase** (all converted).

## New-improvement hunt (in progress)

Measuring full `recap`, `corpus_importer`, `scrapers`, `opinion_page`, `api` modules
(previously only spot-measured) to surface any hidden slow classes worth optimizing.

## New-improvement hunt — results

Measured full `recap, corpus_importer, scrapers, opinion_page, api` modules (`--keepdb
--parallel 1 --durations`).

| Module | Tests | Total | Notes |
|---|---|---|---|
| recap | 185 | 4.5s | fast |
| corpus_importer | 154 | 20.5s | **one 15.4s outlier (below)** |
| scrapers | 82 | 17.5s | a few 1-2.5s ingestion tests; nothing TransactionTestCase-shaped left |
| opinion_page | 81 | 6.7s | fast |
| api | 198 | 9.0s | fast |

**Outlier: `corpus_importer…ScotusDaemonIntegrationTest.test_probe_creates_docket_and_metadata` = 15.4s.**
Investigated: NOT the seeded `high=20000` watermark (reducing it changed nothing), NOT a
mockable `time.sleep` (the daemon's sleep is already mocked). The time is real work inside
the `merge_scotus_docket` production pipeline that the integration test deliberately
exercises (object creation + likely one-time eyecite/ES warmup amortized in a full suite
run). **No safe test-only speedup** without changing coverage or production code — left as-is.

**Pre-existing fragility found (NOT introduced here, NOT fixed):** several tests assume a
`Court(pk="test")` / `recap-email` `User` created by *other* tests/fixtures and fail in
isolation (`DupcheckerPressOnTest`, `api.CoverageTests`, `opinion_page.CitationRedirectorTest`
fixture FK, recap email tests). This is a cross-test data-dependency smell exposed by
isolated/`--keepdb` runs; the normal parallel full-suite run masks it. Worth a separate
cleanup pass (give each class its own `setUpTestData`), but it's risky coverage work,
out of scope here.

## Session end state

- **Committed & pushed** (branch `morgan/test-perf`): 7 `TransactionTestCase` ES conversions + audit report.
- **Uncommitted (for review):** `users` `LiveServerTestCase`→`TestCase`; `search.LLMCleanDocketNumberTests`
  `TransactionTestCase`→`TestCase`; alerts percolator setUpClass+doc-clear rewrite
  (`OpinionAlertsPercolatorTest`, `RECAPAlertsPercolatorTest`, ~3.9s); `base.py` selenium
  ES-rebuild opt-in flag + `AlertSeleniumTest` opt-out (low value); this report.
- **Zero `TransactionTestCase` / non-selenium `LiveServerTestCase` classes remain.**
- **Total measured reclaim: ~228s** (the 8 ES `TransactionTestCase`/`LiveServer` conversions, 43 tests).

---

# PART 9 — Three MISSED `TransactionTestCase` ES classes (the "zero remain" claim was wrong)

The PART 8 "zero `TransactionTestCase` remain" conclusion was **incorrect**. A re-sweep found
three more `TransactionTestCase` ES classes (the audit had examined `tests_es_recap.py` only
for `RECAPSearchTest`/filter tests, and never reached the indexing classes near the end of the
9.4k-line file). All three are the same proven patterns and were converted + verified
(`--keepdb --parallel 1`); **no assertion or expected value changed** (diff-audited).

| Class | File | Tests | Before | After | Pattern |
|---|---|---|---|---|---|
| `RECAPIndexingTest` | search/tests_es_recap.py | 13 | 91.2s | **5.7s** | signal capture-wrap ×65 (incl. nested-in-mock for the two task-count tests) |
| `IndexDocketRECAPDocumentsCommandTest` | search/tests_es_recap.py | 6 | 36.7s | **5.0s** | command tests → `testing_mode=True` (streaming bulk) on every `call_command` |
| `ParentheticalESSignalProcessorTest` | search/tests_es_parenthetical.py | 5 | 30.2s | **4.3s** | signal capture-wrap (incl. nested-in-mock + version/task-count asserts) |
| **TOTAL** | | **24** | **~158s** | **~15s** | **~143s reclaimed** |

Combined single run of all 24 tests: **13.4s** (vs ~158s). **~91% faster.**

### Notes
- `ParentheticalESSignalProcessorTest` / `RECAPIndexingTest`: pure signal-driven indexing — each
  index-triggering op wrapped in `captureOnCommitCallbacks(execute=True)`, ES reads/asserts left
  outside; for the exact-task-count tests the capture is nested **inside** the `mock.patch(...).si`
  so the on-commit `.si` is still counted. `test_prepare_parties` and
  `test_search_pagination_results_limit` needed **no** change (no real indexed-ES reads).
- `IndexDocketRECAPDocumentsCommandTest`: the command does explicit bulk indexing, not signals.
  The default `index_parent_and_child_docs` path already hardcodes `use_streaming_bulk=True`, but
  the `document_type`-filtered path is gated on the command's `--testing-mode` flag — so every
  `cl_index_parent_and_child_docs` call got `testing_mode=True` (transport-only; assertion-neutral).
- **One small production change** (flagged): `ready_mix_cases_project` had no `--testing-mode`
  passthrough, so its `parallel_bulk` path is incompatible with `TestCase`
  (`test_index_dockets_in_bulk_task`). Added a `--testing-mode` arg that forwards
  `testing_mode` to `index_dockets_in_bulk.si(...)` — matches the established PR #3324 convention,
  default `False`, behavior-neutral for the only other callers (which use `task=set-latest-case-ids`,
  a different code path).

**Revised grand total reclaim across the whole effort: ~228s (PART 7) + ~143s (here) ≈ ~371s.**
**There are now genuinely zero `TransactionTestCase` / non-selenium `LiveServerTestCase` classes
left** (re-grepped: the only remaining `TransactionTestCase` references are the base-class
definition in `cl/tests/cases.py`, the test-runner infra in `cl/tests/runner.py`, and a comment
in `cl/search/tasks.py` — none are test classes).

**Status:** applied in the working tree, ruff-clean, pre-commit passes. Not committed.

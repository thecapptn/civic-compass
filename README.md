# Civic Compass

A nonpartisan U.S. election-awareness service. It answers four questions for a given address —
**which elections apply to me, when can I vote, where can I vote, and what is on my ballot** — and it
shows the source, the status, and the verification date for every fact it displays.

It is currently seeded with **demonstration data**. Every election, date, contest, candidate,
measure, location, and result in the repository is invented and is labeled as such on every page and
in every API response. Jurisdictions, election offices, and official source URLs are real, because
the product's floor — *"we do not have this, here is your election office"* — has to actually work.

---

## What makes this different from a typical civic app

**Provenance is a foreign key, not a footnote.** No row in any fact table can be written without a
`source_record_id`. It is `NOT NULL` with a foreign key, so a fact without a source cannot exist in
the database, and a test asserts the constraint is still there.

**Status is computed on read, never trusted from storage.** Stored status is only what the ingest
claimed. On every request the resolver recomputes it from source tier agreement and freshness. A
record whose verification window has expired is automatically downgraded to *"Not yet confirmed."*
Staleness is a status change, not a visual hint.

**Disagreement is shown, not resolved.** When two tier-one election authorities publish different
values, the record becomes `conflicting`, both sources are displayed, and the reader is routed to the
election office. In checklists the earlier of two dates is displayed because acting early is the
recoverable error — and the interface says that it is doing this.

**Absence is a statement.** An uncovered contest never renders as an empty list, because an empty
list reads as *"there is nothing on your ballot."* It renders as an explicit gap with the office
that can answer.

**Neutrality is structural.** Candidate ordering is computed at render time from a rule stated on the
page; there is no stored order, and the schema has no `rank`, `score`, `featured`, or `weight`
column to edit. Every candidate and measure renders through one shared Jinja macro, so unequal
treatment would require changing the template for everyone at once. Fourteen automated checks
(N1–N14) enforce this and fail the build.

**Privacy is structural too.** The address is accepted by POST only, resolved to jurisdiction IDs
inside a single request, and discarded — it is never written, logged, or placed in a URL. There is no
column anywhere in the schema for a political preference, so building the prohibited product would
require a migration.

---

## Running it

```bash
docker compose up --build          # http://localhost:6021
```

Or without Docker:

```bash
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --port 6021
```

Operations console: `http://localhost:6021/ops?token=demo-ops-token`
(set `CIVIC_COMPASS_OPS_TOKEN` for anything beyond localhost).

```bash
make test        # 236 tests
```

### A tour of the seeded data

The demo set is built to exercise the failure modes, not the happy path:

| Try | What it demonstrates |
|---|---|
| `/elections?j=j-minneapolis` | Five overlapping jurisdictions from one location |
| `/elections/e-mn-2026-general?j=j-minneapolis` | Two authorities disagreeing on the mail-return deadline |
| `/ballot/e-mn-2026-general?j=j-minneapolis` | A withdrawn candidate kept and marked; a contest with no data; a partially covered contest; unanswered questionnaire items |
| `/where/e-mn-2026-general?j=j-minneapolis` | A polling place whose verification lapsed, downgraded automatically |
| `/results/e-mn-2026-primary` | A certified contest and an uncertified one on the same page |
| `/elections?j=j-stpaul` | Aggregated third-party data, labeled and never promoted to official |
| `/elections?j=j-wi` | A jurisdiction we cover only at the referral floor |
| `/methodology` | Coverage matrix and source health, generated from the live database |

---

## Layout

```
docs/     Nine pre-implementation artifacts: coverage matrix, source hierarchy, data model,
          threat and privacy model, user flows, content inventory, accessibility test plan,
          neutrality test plan, launch checklist.
app/
  schema.sql   Canonical schema. Provenance enforced by constraint.
  logic.py     Status resolution, freshness windows, neutral ordering, timezone math, ICS.
  repo.py      Read layer. Nothing returns a bare row; every fact carries status and source.
  main.py      Routes: pages, JSON API, operations console.
  seed.py      Demonstration dataset.
  templates/   Server-rendered Jinja. `_macros.html` is the shared candidate/measure template.
  static/      One stylesheet, one progressive-enhancement script.
tests/    236 tests across jurisdiction matching, dates and timezones, freshness, neutrality,
          conflicts and gaps, results status, accessibility markup, corrections, provenance,
          privacy, and voice.
```

## Accessibility

Targets WCAG 2.2 AA. Every page is server-rendered and complete with JavaScript disabled — the
script adds copy buttons and checklist persistence, and nothing else. Status is always carried by a
word; color only ever reinforces text that already says the same thing. Locations are a list first,
with a map as an optional enhancement that is never required. `docs/07` covers the manual test
matrix that the automated checks cannot replace.

## Known limits

Address matching is a ZIP and place-name lookup against seeded hints, not real geocoding or boundary
resolution. Production would need a privacy-conscious geocoder and versioned district boundaries,
with the same rule as everything else: no retention, and jurisdiction IDs only past the request
boundary. There are no live ingestion adapters yet; `docs/02` specifies the contract they have to
meet, including rejection at write time for any adapter that cannot supply a source URL.

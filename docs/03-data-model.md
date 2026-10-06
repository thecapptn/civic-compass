# 03 — Canonical data model

## Principles

1. **Election-scoped identity.** Political geography changes. A contest, a location, and a district
   are only meaningful *for a given election*. Every fact row carries `election_id` where applicable
   and is never reused across elections by name.
2. **Provenance is not metadata, it is a required column set.** No fact table may be written without
   a `source_record_id`. Enforced by foreign key, not by convention.
3. **Append-only facts.** Corrections create a new version with `supersedes_id`; nothing is updated in
   place. `is_current` is derived at read time.
4. **Status is computed, not stored as truth.** Stored status is the ingest-time claim; the resolver
   recomputes effective status from tier agreement + freshness on every read.
5. **No user political data. Ever.** There is no column anywhere for party preference, inferred
   ideology, candidate affinity, or click-through on a candidate record. The schema makes the
   prohibited product impossible to build without a migration.

## Entities

```
jurisdiction        id, name, type(state|county|municipality|school|judicial|special|federal),
                    parent_id, state_code, ocd_id, boundary_version, official_url,
                    office_name, office_phone, office_email, office_address, timezone

district            id, jurisdiction_id, type, name, number, boundary_version, source_record_id

election            id, name, type(general|primary|special|runoff|recall|municipal|school|
                    judicial|measure_only), election_date, timezone, jurisdiction_id,
                    cycle, is_demo, status, source_record_id

election_jurisdiction   election_id, jurisdiction_id   -- an election spans many jurisdictions

deadline            id, election_id, jurisdiction_id, action(register|request_ballot|
                    early_vote_start|early_vote_end|return_postmark|return_receipt|
                    cure|election_day), occurs_at, timezone, is_all_day, scope_note,
                    exception_text, source_record_id

voting_location     id, election_id, jurisdiction_id, type(election_day|early|drop_box|office),
                    name, address_line, city, state_code, postal_code, lat, lon,
                    hours_text, date_range_text, accessibility_text, languages_text,
                    transit_text, source_record_id

rule                id, jurisdiction_id, category(eligibility|id|registration|party|mail|
                    provisional|assistance|language|uocava), title, body_text,
                    effective_date, source_record_id

contest             id, election_id, jurisdiction_id, district_id, office_name, seats,
                    term_text, classification(partisan|nonpartisan|retention|measure|unspecified),
                    ballot_order_official, order_rule(alphabetical|official_ballot|rotating),
                    coverage_note, source_record_id

candidate           id, contest_id, ballot_name, sort_key, filing_status(filed|qualified|
                    withdrawn|disqualified|write_in), party_label_official, incumbent_source,
                    website_url, filing_url, bio_text, bio_provided_by, source_record_id

questionnaire_item  id, contest_id, position, prompt          -- identical set per contest
questionnaire_resp  id, candidate_id, item_id, response_text, responded_at, source_record_id
                    -- absence renders as "No response provided", never hidden

measure             id, contest_id, official_title, ballot_text, measure_type, summary_text,
                    fiscal_note, full_text_url, source_record_id
measure_argument    id, measure_id, stance(for|against), body_text, submitted_by,
                    source_record_id     -- equal count and equal treatment required

result              id, contest_id, candidate_id|measure_option, votes, precincts_reporting,
                    precincts_total, reporting_status(unofficial|canvassing|recount|
                    certified|amended), reported_at, source_record_id

source_record       id, organization, source_url, source_type, trust_tier(1-4),
                    jurisdiction_id, election_id, retrieved_at, published_at,
                    content_hash, claimed_status, notes

record_version      id, entity_table, entity_id, supersedes_id, changed_at, changed_by,
                    change_reason, source_record_id, previous_value_json

audit_log           id, at, actor, action, entity_table, entity_id, source_record_id, note

correction_report   id, submitted_at, entity_table, entity_id, issue_type, body_text,
                    contact_optional, moderation_status(new|triage|confirmed|rejected|fixed),
                    resolution_note, resolved_at
                    -- public-facing status only; contact is optional and purgeable

saved_plan          token, created_at, expires_at, jurisdiction_id, election_id,
                    method_pref, checklist_state_json
                    -- opaque token, no identity, hard TTL, device-local by default
```

## Derived, never stored

- Effective status (`official` / `verified` / `aggregated` / `pending` / `conflicting` / `historical`)
- Days remaining to a deadline (computed in the jurisdiction's timezone at request time)
- Coverage matrix cells
- Candidate display order (recomputed per render from `order_rule`, so ordering cannot be
  hand-edited in the database)

## Ordering rule

Default `order_rule` is `alphabetical` on `sort_key`, which is derived as
`lower(last_name) || '\u0000' || lower(first_name)` at write time. `official_ballot` order may be used
**only** when the source is tier 1 and the UI labels it "Official ballot order." There is no
`relevance`, `popularity`, or `featured` ordering, and no column to store one.

## Timezones

`occurs_at` is stored UTC. `timezone` is the jurisdiction's IANA zone. All display and all
"days remaining" math happens in the jurisdiction's zone, not the browser's — a mail-ballot deadline
of 8:00 PM local is a legal fact about the jurisdiction, not about where the user is sitting.

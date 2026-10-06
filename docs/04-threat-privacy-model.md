# 04 — Threat and privacy model

## What makes this product a target

A civic-information tool is attractive to attackers for reasons unrelated to its size. The assets are
not credit cards; they are **the ability to tell many people a false fact about voting**, and
**a list of people who intend to vote and where they live**.

## Assets

| Asset | Why it matters | Primary protection |
|---|---|---|
| Displayed election facts | A wrong deadline or location suppresses votes at scale | Append-only records, tier-1 gating, two-person review on high-risk fields, source strip on every fact |
| Address / ZIP entered | Location data revealing residence + voting intent | Not persisted by default, never logged, never in a URL |
| Saved plan tokens | Links a device to a jurisdiction and election | Opaque token, no identity, hard TTL, local-first |
| Correction reports | May contain contact info | Optional field, purgeable, not indexed |
| Ops console | Direct write access to public facts | Separate auth, role-based, every action audited |
| Source URLs | Poisoning upstream shifts everything downstream | Content hashing, change detection, conflict surfacing |

## Threats and mitigations

**T1 — Suppression by injected falsehood.** An attacker changes a polling place or deadline.
*Mitigation:* no path writes a fact without a `source_record`; high-risk classes require tier 1;
changes to `DEADLINE` / `LOCATION` / `RULES` require two-person review; every change is diffed into
`record_version` with the previous value retained; the public "What changed" panel makes silent edits
visible; automated tests assert no fact renders without provenance.

**T2 — Suppression by omission.** An empty contest list reads as "nothing to vote on."
*Mitigation:* coverage levels are first-class; `none` and `pending` render explicit text and an office
referral; a test asserts that an empty section never renders as an empty list.

**T3 — Upstream source compromise or scrape drift.** A source page changes shape and the adapter
silently ingests garbage.
*Mitigation:* content hashing, sanity ranges on dates, conflict detection against prior version,
freshness expiry that downgrades rather than serves stale data, source-health dashboard.

**T4 — Political targeting via the product.** Someone builds an audience from users' jurisdictions.
*Mitigation:* no accounts required; no political preference field exists in the schema; no
candidate-specific notifications; no ad tech, no third-party analytics, no fingerprinting; reminders
are device-local or calendar files generated client-side.

**T5 — Address re-identification through logs.** Addresses leaking into access logs, error traces,
referrers, or analytics.
*Mitigation:* location resolution is `POST` only, never a query string; addresses are truncated to
jurisdiction immediately and the raw string is discarded before any handler returns; access logging
strips bodies; error reports carry no request body; `Referrer-Policy: no-referrer`.

**T6 — Neutrality capture.** Pressure or paid interest to reorder, feature, or soften a record.
*Mitigation:* ordering is computed at render from `order_rule` with no override column; identical
templates enforced by a single shared partial; neutrality tests fail the build on template drift;
governance charter prohibits paid placement; changes to candidate records are audited like any
other fact.

**T7 — Impersonation of the product.** Cloned site with altered deadlines.
*Mitigation:* every page links out to the official election office; the product's own copy repeatedly
frames the official office as the authority, so a user who lands on a clone still has the habit of
verifying.

**T8 — Result confusion.** Unofficial numbers screenshot and shared as final.
*Mitigation:* reporting status is text, not color; "unofficial" appears in the record itself, not just
a page banner; certified results carry the certifying authority and date; canvass explained in plain
language on the same page.

**T9 — Denial of service near election day.** Traffic spike coinciding with peak need.
*Mitigation:* fully cacheable read layer, static-friendly pages that work without JavaScript, no
per-user rendering on the critical path, rate limiting on writes only, graceful degradation to the
office-referral card.

## Data retention

| Data | Retention |
|---|---|
| Entered address | Never written to disk; discarded within the request after jurisdiction resolution |
| Resolved jurisdiction | Session/URL only, user-visible and user-clearable |
| Saved plan | Device-local by default; server-side token expires ≤ 120 days after the election |
| Correction report | Retained through resolution + 1 year; contact field purged on resolution |
| Audit log | 7 years — this is the accountability record, not user data |
| Access logs | 30 days, no bodies, IP truncated |

## Privacy commitments rendered in the product

The methodology page states, in plain language: what we store, what we do not store, how long, how to
delete a saved plan, that we do not infer political preference, and that we do not sell or share
location data. Anything we cannot honestly claim, we do not claim.

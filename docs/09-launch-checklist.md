# 09 — Launch checklist

Two gates: a **product gate** (once, before any public traffic) and a **jurisdiction gate** (every
jurisdiction, every election cycle). A jurisdiction that fails its gate is not launched degraded — it
is left at the office-referral floor, which is a correct answer.

## Product gate

### Data integrity
- [ ] No fact table row can be written without a `source_record_id` (enforced by constraint, verified by test)
- [ ] Append-only versioning in place; previous values retained and inspectable
- [ ] Freshness expiry downgrades records automatically; verified by test with a frozen clock
- [ ] Conflicting tier-1 sources render as `conflicting` with both sources and an office referral
- [ ] Demo data cannot render without the demo banner (verified by test)

### Neutrality
- [ ] All N1–N14 automated checks pass
- [ ] Shared-partial template review signed off by a second reviewer
- [ ] Reversed-seed order audit produces identical output
- [ ] Independent neutrality review complete and published

### Accessibility
- [ ] Automated markup checks pass on every route
- [ ] Manual keyboard, screen reader, zoom, contrast, reduced-motion, forced-colors checks pass
- [ ] Every critical flow completes with JavaScript disabled
- [ ] Third-party audit complete; report published on `/methodology`

### Privacy and security
- [ ] Address accepted by POST only; never in a URL, log, referrer, or error trace
- [ ] Raw address discarded within the request; jurisdiction only thereafter
- [ ] No third-party analytics, ad tech, or fingerprinting on any page
- [ ] Saved plans are opaque, expiring, and deletable by the user in one action
- [ ] No schema field can store political preference or inference
- [ ] Ops console behind separate auth with role-based permissions
- [ ] Secrets outside client code and outside the repository
- [ ] Dependency scan clean; backup restore rehearsed
- [ ] `Referrer-Policy: no-referrer`, CSP, HSTS, and frame protections set

### Content and trust
- [ ] Glossary complete for every jargon term used in the interface
- [ ] Every dead end routes to the office-referral card
- [ ] Certification, canvass, and recount explainers reviewed by an election administrator
- [ ] `/methodology` published: sources, matching, freshness, what we do not know, corrections, privacy
- [ ] Correction workflow end-to-end tested including public status lookup
- [ ] Governance charter published; correction SLA defined and staffed

### Operations
- [ ] Source-health dashboard live with per-source last-success and drift alerts
- [ ] Stale-data alerting paging a named on-call during the final 60 days
- [ ] Candidate-withdrawal and location-change runbooks written and rehearsed
- [ ] Load tested at expected election-week peak with cache cold
- [ ] Rollback plan and a static fallback page that still names the election office

## Jurisdiction gate (per jurisdiction, per cycle)

- [ ] `ADMIN` record verified within 90 days: office name, official URL, phone, email, address
- [ ] Named data steward with correction SLA accountability
- [ ] Address-to-jurisdiction matching tested against ≥ 20 representative addresses including split
      precincts, recent annexations, overlapping school districts, and PO boxes
- [ ] Election dates and all deadlines source-linked, timezone-resolved, and independently spot-checked
- [ ] Locations verified or explicitly marked pending; list view complete without the map
- [ ] Contest coverage explicit; incomplete coverage stated in words on the ballot page
- [ ] Candidate records use neutral ordering, identical fields, and correct filing status
- [ ] Measure official title and full text linked to the authority
- [ ] Results pipeline distinguishes unofficial from certified, with the certifying authority named
- [ ] Accessibility and neutrality checks re-run against this jurisdiction's rendered pages
- [ ] Coverage matrix row published and matching the database

## Post-launch, continuous

- [ ] Weekly source-health review; daily inside 60 days; hourly on election week
- [ ] Correction queue triaged within SLA; public status kept current
- [ ] Post-election: results tracked through canvass, certification, and any recount
- [ ] Coverage matrix regenerated; jurisdictions that went stale downgraded publicly
- [ ] Annual transparency report published

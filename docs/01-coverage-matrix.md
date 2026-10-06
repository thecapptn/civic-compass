# 01 — Coverage matrix

Coverage is a **public, per-jurisdiction, per-data-class claim**. If we cannot name the source for a
data class in a jurisdiction, that cell is `none` and the UI says so in words. We never let an empty
cell render as an empty list, because an empty list reads as "there is nothing on your ballot."

## Data classes

| Code | Data class | Risk tier | Why the tier |
|---|---|---|---|
| `ELECTION` | Election exists, name, date, type | High | Wrong date = missed election |
| `DEADLINE` | Registration / request / return / early-vote windows | High | Time-barred; no remedy after the fact |
| `LOCATION` | Election Day sites, early sites, drop boxes, offices | High | Changes late; sends people to wrong place |
| `RULES` | Eligibility, ID, party participation, provisional, assistance | High | Legal consequence if wrong |
| `CONTEST` | Offices and districts on the ballot | Medium | Omission implies contest does not exist |
| `CANDIDATE` | Ballot names, filing status, party label | Medium | Neutrality-sensitive |
| `MEASURE` | Official title, ballot text, fiscal note | Medium | Text fidelity matters |
| `RESULT` | Reported and certified results | High | Certification confusion |
| `ADMIN` | Election office identity, contact, official URL | High | The fallback for every other class |

## Coverage levels

| Level | Definition | UI consequence |
|---|---|---|
| `official` | Ingested from the responsible election authority | Show normally, with source strip |
| `verified` | Reconciled against an authority inside the freshness window | Show normally, with source strip |
| `aggregated` | Third-party provider only, not yet reconciled | Show with provenance warning |
| `partial` | Some records present, coverage known incomplete | Show + explicit "this list may be incomplete" |
| `pending` | Expected but not yet published | Show the gap, name what is missing, link office |
| `none` | Not covered | Do not render the section; render the referral card |

## Launch matrix (demo build)

`ADMIN` must be `official` before any other class in a jurisdiction may render. That is the hard gate.

| Jurisdiction | ELECTION | DEADLINE | LOCATION | RULES | CONTEST | CANDIDATE | MEASURE | RESULT | ADMIN |
|---|---|---|---|---|---|---|---|---|---|
| Minnesota (state) | official | official | partial | official | official | official | official | pending | official |
| Hennepin County, MN | official | official | official | official | official | official | none | pending | official |
| City of Minneapolis, MN | official | official | official | verified | official | official | official | pending | official |
| Minneapolis Public Schools | official | official | partial | verified | official | official | none | pending | official |
| Ramsey County, MN | official | official | pending | official | partial | aggregated | none | pending | official |
| City of Saint Paul, MN | official | official | pending | verified | partial | aggregated | none | pending | official |
| Wisconsin (state) | official | partial | none | official | none | none | none | none | official |
| All other jurisdictions | none | none | none | none | none | none | none | none | official |

`ADMIN` is `official` nationwide because the NASS/CanIVote and USA.gov office directories let us always
answer "who administers your election, and how do you reach them." **That referral is the product's
floor.** A jurisdiction we know nothing else about still gets a correct, useful answer.

## Gate to promote a jurisdiction

1. `ADMIN` record with official URL, verified within 90 days.
2. A named ingestion adapter, or a logged manual-entry procedure with a two-person review.
3. `ELECTION` + `DEADLINE` at `official`, timezone-resolved, with a source URL per record.
4. Jurisdiction-matching tested against at least 20 representative addresses, including the edge cases
   in `docs/07` (split precincts, annexations, PO boxes, overlapping school districts).
5. Accessibility and neutrality checks pass on the rendered pages for that jurisdiction.
6. A named data steward accountable for the correction SLA.

## Public coverage page

`/methodology#coverage` renders this matrix from the database, not from this document, so the published
claim and the shipped data cannot drift apart. Any cell whose supporting records have gone stale
downgrades automatically to `pending` and is reported on the source-health dashboard.

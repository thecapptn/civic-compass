# 02 — Source hierarchy and reconciliation

Sources are ranked by **administrative authority over the fact in question**, never by reputation,
popularity, or political identity. Authority is per-fact: a state agency is authoritative for statewide
registration deadlines but not for a city drop-box location.

## Trust tiers

| Tier | Source class | Authoritative for | Max status it can confer |
|---|---|---|---|
| 1 | Responsible local election authority (county auditor, city clerk, board of elections) | Polling locations, hours, local contests, local measures, sample ballots, local results | `official` |
| 1 | State election authority (Secretary of State / State Board) | Election dates, registration rules, ID rules, statewide contests, certification | `official` |
| 2 | Federal reference (USA.gov, EAC, FVAP) | National explanations, UOCAVA guidance, accessibility guidance, canvass/certification concepts | `verified` |
| 2 | NASS / CanIVote.org | Locating the responsible office | `verified` |
| 3 | Licensed civic-data provider | Coverage and standardization | `aggregated` |
| 4 | Product-authored explanation | Plain-language definitions only | `explanatory` |

Tier 4 may never carry a jurisdiction-specific legal claim. Product-authored copy explains what a
runoff *is*; it never states when *your* runoff is.

## Fixed reference sources

- USA.gov — how, when, and where to vote: <https://www.usa.gov/how-to-vote>
- USA.gov — state and local election offices: <https://www.usa.gov/state-election-office>
- NASS TrustedInfo: <https://www.nass.org/initiatives/trustedinfo>
- CanIVote.org: <https://www.canivote.org>
- EAC voting accessibility: <https://www.eac.gov/voting-accessibility>
- EAC canvass and certification: <https://www.eac.gov/election-officials/election-results-canvass-and-certification>
- FVAP: <https://www.fvap.gov/>

## Reconciliation

Every ingested fact is stored as a `source_record` bound to a `(jurisdiction, election, field)` key.
Multiple records for one key are expected and are **not** an error.

Resolution order:

1. **Single tier-1 record** → status `official`.
2. **Multiple tier-1 records that agree** → `official`, all sources listed.
3. **Tier-1 + lower tier that agree** → `verified`, tier-1 shown first.
4. **Tier-1 + lower tier that disagree** → tier-1 wins, status `verified`, the disagreement is logged
   to the ops queue but is not shown to the public. Lower tiers do not get to cast doubt on an
   authority.
5. **Two tier-1 records that disagree** → status `conflicting`. Both values shown, both sources linked,
   the user is routed to the election office. We do not pick a winner. This is the case the
   product exists to handle honestly.
6. **No tier-1, only tier-3** → `aggregated`, provenance warning shown.
7. **Expected but absent** → `pending`, with the gap named.

Conflicts on high-risk classes (`DEADLINE`, `LOCATION`, `RULES`, `RESULT`) page a steward immediately.
Conflicts on medium-risk classes enter the normal queue.

## Freshness windows

Freshness is a function of risk tier and proximity to election day. Exceeding the window downgrades
the record to `pending` **automatically** — staleness is not a display nuance, it is a status change.

| Data class | > 60 days out | ≤ 60 days | ≤ 14 days | Election week |
|---|---|---|---|---|
| `ELECTION` | 90 d | 30 d | 14 d | 3 d |
| `DEADLINE` | 45 d | 14 d | 7 d | 1 d |
| `LOCATION` | 45 d | 14 d | 3 d | 1 d |
| `RULES` | 90 d | 30 d | 14 d | 7 d |
| `CONTEST` / `CANDIDATE` / `MEASURE` | 60 d | 21 d | 7 d | 3 d |
| `RESULT` (unofficial) | — | — | — | 1 h |
| `RESULT` (certified) | never expires | | | |

## Ingestion adapter contract

Every adapter must emit, per record: source organization, source URL, source type, retrieval time,
publication or update time as reported by the source, jurisdiction ID, election ID, effective date,
a content hash, and a trust tier. An adapter that cannot supply a source URL is not an adapter and
its output is rejected at write time, not at review time.

Adapters never overwrite. They append a new version and let the resolver decide, so every prior value
stays inspectable in the audit log.

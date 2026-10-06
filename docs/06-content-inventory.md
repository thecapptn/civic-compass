# 06 — Content inventory

## Routes

| Route | Area | Renders without JS | Notes |
|---|---|---|---|
| `/` | Home | yes | Location entry, browse by state, help entry |
| `/resolve` (POST) | — | yes | Form target; address never in URL |
| `/confirm` | Home | yes | Jurisdiction confirmation |
| `/elections` | Elections | yes | Filterable via query links |
| `/elections/{id}` | Elections | yes | Election detail + status banner |
| `/plan/{id}` | My election plan | yes | Checklist, print, .ics, save |
| `/plan/{id}/print` | My election plan | yes | Print stylesheet |
| `/plan/{id}/calendar.ics` | My election plan | yes | Text/calendar download |
| `/ballot/{id}` | My ballot | yes | Neutral contest preview |
| `/contest/{id}` | My ballot | yes | Candidate detail, neutral ordering |
| `/measure/{id}` | My ballot | yes | Official text, equal-treatment arguments |
| `/where/{id}` | Where to vote | yes | List-first locations |
| `/rules` | Voting rules | yes | Jurisdiction rules by category |
| `/results/{id}` | Results | yes | Unofficial vs certified |
| `/help` | Help and report | yes | FAQ, glossary, office finder |
| `/report` | Help and report | yes | Correction form |
| `/report/{id}` | Help and report | yes | Public status of a report |
| `/methodology` | Help and report | yes | Sources, coverage, privacy, changelog |
| `/ops` | Internal | yes | Token-gated operations console |
| `/api/*` | Internal/public read | n/a | JSON mirror of the read layer |

## Global components

Status banner · source strip (the provenance receipt) · deadline card · election card · contest card ·
candidate card · measure card · location card · coverage notice · conflict notice · office referral card ·
glossary term · correction link · language selector · print view · skip link.

**The source strip is required on every rendered fact.** It carries: status word, source organization,
source link, jurisdiction, election ID, retrieved timestamp, last verified timestamp. It is rendered by
one shared template partial so it cannot vary between a candidate and a measure.

## Glossary (product-authored, jurisdiction-neutral)

primary · runoff · recall · special election · ballot measure · precinct · provisional ballot ·
absentee / mail ballot · ballot cure · canvass · certification · recount · sample ballot ·
partisan vs nonpartisan contest · retention election · at-large seat · UOCAVA.

Each definition explains the concept generally, then says: *"Rules for this term vary by state. Check
your election office for how it works where you vote."*

## Voice rules (enforced by test)

Banned in product-authored copy: save democracy, take back, extreme, radical, common sense, real voters,
patriots, crucial, historic, high-stakes, fight, defend, battleground, must-win, refused to answer,
cut through the noise, spin.

Required constructions:

| Situation | Copy |
|---|---|
| Address match | "We found these jurisdictions for this address. Confirm before viewing your ballot." |
| Uncertainty | "This information has not yet been confirmed by the responsible election office." |
| Conflict | "Two sources show different information. Check the official election office before acting." |
| Candidate info | "This information is provided for reference and does not represent an endorsement." |
| Unanswered | "No response provided." |
| Results | "These results are reported but not certified. Numbers may change during canvass." |
| Missing data | "We do not yet have reliable data for this contest. Contact your local election office." |
| Eligibility | "You may be eligible" — never "You are eligible" |
| Attribution | "The official election office lists…" — never "The correct answer is…" |

## Demo-data labeling

While seeded with demo data the product must, on every page: render a non-dismissible banner naming the
data as demonstration data, prefix every demo election name, badge every demo record, and set
`status = demo` in the API. A test asserts that no page renders a demo record without the banner.

# 05 — User flows

Every flow has a **defined failure path**, because the honest answer is often "we do not have this yet."
A flow without a failure path is not designed.

## Flow A — Resolve location → upcoming elections

```
Home
  └─ enter address | ZIP | choose state → county → municipality
       └─ POST /resolve   (never GET — address must not enter a URL)
            ├─ confident match  → confirmation screen: state, county, municipality,
            │                     school district, districts, match confidence, "not right? edit"
            ├─ ambiguous        → disambiguation list, no auto-pick
            └─ no match         → state picker + office referral card
                 └─ /elections?j=<jurisdiction_id>   (jurisdiction ID in URL, address never)
                      ├─ elections found → list: date, type, jurisdiction, why-relevant, status
                      └─ none found      → "No elections on file for this jurisdiction." +
                                           coverage level + office link + report-a-gap
```

Filters: all / within 30 days / registration open / voting available now. Filters are links with
real URLs, not JavaScript state, so they survive sharing and work without scripting.

## Flow B — Build a voting plan

```
/elections/{election_id}?j=...
  └─ choose method: Election Day | early in person | mail | drop off | military/overseas | not sure
       └─ /plan/{election_id}?j=...&m=...
            ├─ checklist built from deadlines applicable to (election × jurisdiction × method)
            ├─ each item: what to do, when (jurisdiction timezone), source strip, official link
            ├─ missing deadline → item still appears, marked "Not published yet" + office link
            └─ actions: print (CSS print view) | .ics export | save to this device | copy link
```

"Not sure" shows every method available in the jurisdiction rather than picking one. The product never
claims the user is registered or eligible; it links to the official verification service and labels
whose determination it is.

## Flow C — Ballot preview

```
/ballot/{election_id}?j=...
  └─ contests grouped: federal → state → judicial → county → municipal → education → special → measures
       ├─ each contest: office, district, seats, term, classification, "Why am I seeing this?"
       ├─ candidates in computed neutral order, order rule stated in words
       ├─ each candidate: identical field set, "No response provided" for gaps
       ├─ withdrawn candidate: shown, marked withdrawn, not removed
       └─ coverage gap → "This contest may be incomplete" or "We do not yet have reliable data
                          for this contest. Contact your local election office." + link
```

Labeled "Ballot preview" unless the jurisdiction supplies an official sample ballot, in which case it is
labeled as such and linked to the original.

## Flow D — Where to vote

```
/where/{election_id}?j=...
  └─ four separate categories, never merged:
       Election Day sites | Early voting sites | Drop boxes | Election offices
         ├─ each: name, address, date range, hours, accessibility, languages, transit,
         │        source strip, last verified, "hours may change" note, copyable address
         ├─ list is primary; map is optional enhancement and never required
         └─ category empty → named as empty, with the reason, plus office link
```

## Flow E — Results and certification

```
/results/{election_id}
  └─ default view: reported results
       ├─ per contest: reporting status in words, precincts reporting, last update,
       │               source link, certifying authority when certified
       ├─ plain-language canvass / certification / recount explainer on the page
       └─ no results yet → "No results have been reported." (never zeros, which read as a tie)
```

## Flow F — Report a correction

```
Any fact → "Report a problem with this information"
  └─ pre-filled with entity reference, no personal data required
       └─ POST /report → public reference ID → status visible at /report/{id}
            └─ ops triage: new → triage → confirmed/rejected → fixed, with resolution note
```

## Flow G — The floor

Reachable from every dead end in every flow above:

```
"We do not yet have reliable data for this."
  └─ Who administers your election: <office name>
     Official website · phone · email · address
     NASS CanIVote · USA.gov office directory
```

This is a **successful** outcome, not an error state, and is written and styled as such.

# 08 — Neutrality test plan

Neutrality is enforced by mechanism, not by policy statement. Each check below is either an automated
test that fails the build, or a signed-off manual review with a named reviewer.

## Automated (`tests/test_neutral_ordering.py`, `tests/test_voice.py`)

| ID | Check | Failure condition |
|---|---|---|
| N1 | Ordering is computed | Any candidate list not sorted by `sort_key` unless `order_rule = official_ballot` and labeled as such |
| N2 | Ordering is stable and input-independent | Shuffling insert order or IDs changes rendered order |
| N3 | No ranking columns exist | Schema contains any of `rank`, `score`, `featured`, `priority`, `promoted`, `match`, `weight` on candidate/measure |
| N4 | Identical field sets | Two candidates in one contest render different field labels or a different field count |
| N5 | Equal visual treatment | Candidate cards differ in class list, wrapper element, or image treatment within a contest |
| N6 | Unanswered is shown, not hidden | A questionnaire item with no response is absent from the rendered card |
| N7 | Equal argument treatment | A measure renders arguments for without arguments against (or vice versa) without an explicit sourced note |
| N8 | Party never encoded as color | Any element carries a party-derived class, style, or color token |
| N9 | Banned vocabulary | Product-authored copy contains any term from the banned list in `docs/06` |
| N10 | No persuasive CTA | Any button or link text containing donate, support, join, pledge, volunteer, sign up for a campaign |
| N11 | Provenance present | Any rendered fact without a source strip |
| N12 | No inference storage | Any write path storing a candidate view, click, or preference |
| N13 | Withdrawn candidates retained | A withdrawn candidate is removed from a rendered contest rather than marked |
| N14 | Neutral empty state | An uncovered contest renders as an empty list rather than an explicit unavailable notice |

## Manual review (per release)

1. **Template diff review.** All candidate and measure rendering must flow through one shared partial.
   Reviewer confirms no per-candidate or per-party branch exists anywhere in the template tree.
2. **Copy review.** Every product-authored string read for loaded framing, implied urgency beyond the
   actual deadline, and implied approval. Reviewer is not the author.
3. **Screenshot parity.** Render every contest in the launch set; overlay candidate cards; confirm
   identical geometry, weight, and spacing.
4. **Order audit.** Re-seed the database with reversed insertion order; confirm byte-identical
   rendered output for all contest pages.
5. **Independent neutrality review.** Before public launch, an external reviewer with no stake in any
   contest checks for paid placement, recommendation behavior, partisan color-coding, and unequal card
   treatment, and their finding is published.

## Governance controls

- No paid placement of any kind, ever. There is no advertising system to abuse.
- Candidate-supplied content is opt-in, identical-prompt, identical-limit, and labeled as
  candidate-supplied. A candidate declining is rendered "No response provided," never "refused."
- Endorsements are omitted by default. If ever included for research context, they require source,
  date, and an equal-standards rule applied to every candidate in the contest.
- Campaign finance is a link to official disclosure, never a ranking and never a fundraising path.
- Two-person review for any change to a candidate or measure record, logged in the audit trail.
- Annual public transparency report: corrections issued, conflicts surfaced, coverage changes,
  neutrality review findings.

## What a failure means

A neutrality test failure blocks release the same way a failing deadline test does. There is no
"ship it and fix the ordering next sprint" path, because unequal presentation of candidates during an
open election cannot be retroactively undone.

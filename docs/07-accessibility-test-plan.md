# 07 — Accessibility test plan

Target: **WCAG 2.2 AA**. Accessibility failures on a critical flow are treated as data errors, because
an instruction a person cannot perceive is functionally an instruction we did not publish.

## Critical flows that must pass end to end

1. Resolve location → confirm jurisdiction → view upcoming elections
2. Open an election → build a plan → read every deadline
3. Open the ballot preview → read every contest and candidate
4. Find a voting location → copy the address
5. Read results and understand certification status
6. Report a correction

## Automated checks (in CI, `tests/test_accessibility_markup.py`)

- Every page has exactly one `<h1>`; heading levels never skip.
- `<html lang>` present and correct; `lang` switches on translated blocks.
- Every `<img>` has `alt`; decorative images use `alt=""`.
- Every form control has a programmatically associated `<label>`; no placeholder-as-label.
- Every `<a>` has discernible text; no bare "click here" / "read more".
- Landmarks present: `header`, `nav`, `main`, `footer`; one `main`; skip link is the first focusable element.
- Tables use `<th scope>`; layout tables are not used.
- No positive `tabindex`.
- Status changes announced via `role="status"` / `aria-live="polite"`, not color alone.
- Every status word appears as **text** — assert that no element conveys status only via a class name
  or background color.
- Buttons vs links used semantically (navigation = link, action = button).
- Touch targets ≥ 24×24 CSS px (WCAG 2.2 AA, 2.5.8).
- Page renders and all critical content is present with scripting disabled.

## Manual checks (per release, per launch jurisdiction)

| Check | Method | Pass condition |
|---|---|---|
| Keyboard only | Tab/Shift-Tab/Enter/Space through each critical flow | Every action reachable, focus visible at all times, no trap, logical order |
| Focus not obscured (2.4.11) | Sticky header/footer over focused element | Focused control never fully hidden |
| Screen reader | NVDA + Firefox, VoiceOver + Safari (desktop and iOS) | Flow completable; status, provenance, and coverage gaps announced |
| Zoom | 200% and 400% at 1280px | No horizontal scroll, no clipped content, no lost function |
| Text spacing (1.4.12) | Line height 1.5×, letter 0.12em, word 0.16em, paragraph 2× | No overlap or truncation |
| Reflow | 320px width | Single column, no two-dimensional scrolling |
| Contrast | Text 4.5:1, large 3:1, UI/graphics 3:1 | All states, including focus and disabled-adjacent |
| Color independence | Grayscale render | Every status still identifiable |
| Reduced motion | `prefers-reduced-motion: reduce` | All non-essential motion removed |
| High contrast / forced colors | Windows HCM | Borders and focus survive |
| No-map path | Disable map | Location list, hours, and copyable address fully usable |
| Dragging (2.5.7) | Any drag interaction | Single-pointer alternative exists |
| Redundant entry (3.3.7) | Multi-step plan flow | Previously entered info not re-requested |
| Accessible authentication (3.3.8) | Saved-plan flow | No cognitive function test required |
| Language | Spanish UI | Interface strings translated; source text labeled as untranslated official text |

## Content accessibility

- Plain-language target around 8th grade for instructional copy; measured per release.
- Every jargon term links to a glossary definition on first use per page.
- Dates written in full ("Tuesday, November 3, 2026"), never numeric-only.
- Times always carry the jurisdiction's timezone in words.
- Instructions never depend on color, hover, position ("the button on the right"), shape, or sound.

## Exit criteria

No automated failures. No manual blockers on any critical flow. Every known issue logged with a
severity, an owner, and a date. Third-party accessibility audit before public launch, and its report
published on the methodology page.

# Design review

Relay uses a technical instrument plus editorial narrative direction from `design.md`. A true black incident ledger carries the real product proof while the long form story explains why fresh session memory changes the next action.

## Rendered QA

Verified in the in app browser at:

- 360 × 800
- 768 × 900
- 1024 × 900
- 1440 × 1000

All four sizes have zero horizontal overflow. Desktop keeps the live evidence console in three columns. Tablet composes the hero and product instrument vertically. Mobile uses Incident, Memory and Receipt tabs with full width touch targets.

## Improvement loop

The highest impact issues found during rendered inspection were:

1. The mobile proof line split its sentence into narrow flex fragments. The copy now has one wrapping container.
2. The full screen menu covered its own close control. The floating navigation now stays above the overlay and preserves the hamburger morph.
3. A state update could remove the reveal class from the live console after it entered the viewport. The working product instrument no longer depends on a transient reveal class.
4. A fresh session produced a receipt but left mobile visitors on the Memory view. The Receipt view now opens automatically when a new session arrives.
5. A long memory detail could stretch a preview row. Its content wrapper now has a strict minimum width and ellipsis behavior.

Interaction checks covered fresh session recall, receipt selection, evidence persistence, journal updates, reset, mobile navigation, legal routes, the custom missing route and disabled form submission. Browser logs were clean.

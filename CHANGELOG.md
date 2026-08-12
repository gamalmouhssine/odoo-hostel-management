# Changelog

## 19.0.1.0.1 — Post-v1.0

92 automated tests, 0 failures. Everything below shipped after v1.0, in response to real
follow-up requests rather than the original phased spec — see `CLAUDE.md`'s Decisions Log
for the reasoning and the bugs each one surfaced along the way.

**Brand refresh**: new **Terracotta & Deep Teal** visual identity (was Modern Navy &
Amber) across kanban cards, list views, form headers/statusbars, and every QWeb report,
plus a redrawn app icon and a new store banner.

**Folio/invoice integrity**: cancelling or deleting an invoice automatically reopens its
folio (`state` back to `open`, lines untouched) so it can simply be re-invoiced; an
invoiced folio itself can't be deleted until its invoice is gone. `hostel.folio.state`
dropped its `paid` value entirely — payment status now reads live off the invoice's own
`payment_state` instead of a second value nothing could reliably keep in sync.

**Deletion-safety guards**: deleting a room or bed with real booking history is blocked
(archive instead) — including via cascade, e.g. deleting a room no longer silently
cascade-deletes beds with booking history behind them. A booking that lost its folio (a
Manager deleted it) gets a one-click **Create Folio** recovery action, and the booking
list surfaces a `folio_status` column so a booking that's missing one is visible without
opening the record.

**Migration scripts**: proper `migrations/<version>/` scripts so an existing database
upgrades cleanly instead of silently keeping stale data (e.g. old `state='paid'` folio
rows get migrated to `invoiced`).

**Live front-desk mechanisms**:
- Arrival, checkout, and overstay reminders as both a chatter/systray activity
  (`mail.activity`) and a live in-app popup notification (bus-based, reaches anyone with
  Odoo open right now) - overstay is alert-only by design, never auto-checks anyone out.
- Confirmed bookings nobody checks in are automatically marked `no_show` once their
  check-in date has fully passed, freeing the room instead of leaving it silently
  blocked.
- Deposit enforcement: check-in is blocked if a deposit was required and never marked
  paid.
- Booking confirmation emails sent to the guest automatically on confirmation (skipped
  silently if the guest has no email on file).
- Housekeeping task assignment popups: the assigned housekeeper is notified live the
  moment a task lands on them or gets reassigned.

## 19.0.1.0.0 — v1.0

Standalone guest-hostel PMS, built phase by phase per [PHASES.md](PHASES.md). 57 automated
tests, 0 failures, verified via a fresh `-i --with-demo` install.

**Master data**: multi-property support (`hostel.property`); room types with sleeping
type, bed type, amenities, photos, and an optional rate plan on top of a flat default
rate; rooms with independent occupancy (`state`) and housekeeping (`housekeeping_status`)
axes; beds with a pure occupancy status (available/booked/occupied/maintenance) plus
female-only/bottom-bunk flags; guests as an extended `res.partner` (ID document, date of
birth, emergency contact, computed stay history) rather than a parallel guest model.

**Bookings**: whole-room or single-bed, with a room/bed overlap constraint that correctly
treats a whole-room booking as blocking every bed inside it and vice versa; price-locked
nightly rate (never moves retroactively if a room type's rate changes later); deposits;
OTA source/reference tracking; a full state machine (draft → confirmed → checked_in →
checked_out, plus cancelled and no_show) with the check-in/check-out actions actually
driving room/bed status, including the partial-occupancy dorm cascade (a room only reads
"occupied" once every bed in it is).

**Billing**: folios auto-open at check-in with a pre-filled stay line; extra charges
(configurable charge types) addable any time the folio is open; one-click invoicing via
standard Odoo Invoicing (`account.move`) with no hardcoded tax rate.

**Housekeeping**: a `checkout_clean` task auto-created on every checkout (deduplicated —
a second checkout on the same room before the first task is cleared doesn't pile up a
duplicate); a one-click "Mark Clean" shortcut that also completes the matching task.

**Views**: a status-colored Room Kanban board; front-desk saved filters (Arrivals Today,
Departures Today, In-House Now); guest quick-create and availability-only room/bed
domains on new bookings.

**Reports**: QWeb PDF booking confirmation, check-in registration card, folio, daily
arrivals & departures, and a date-range occupancy/ADR summary wizard; revenue/occupancy
pivot and graph views.

**Security**: a separate, independently-assignable Housekeeping role (not a tier under
Staff); property-scoped access for Staff/Housekeeping via an assigned-properties field on
`res.users` (Manager always unrestricted; no properties assigned means unrestricted, not
locked out); field-level protection on guest ID documents.

**Descriptive/configuration values are editable models, not hardcoded picklists**:
amenities, bed types, sleeping types, ID document types, cancellation policies, booking
sources, charge types, and housekeeping task types can all be extended from the UI
without a code change. Workflow-state fields (booking state, room state/housekeeping
status, bed status, housekeeping task state) stay hardcoded Selections, since Python
methods branch on their exact values.

**Explicitly out of scope for v1.0**: POS folio integration, a guest-facing portal, OTA
channel-manager live sync (only manual `source`/`external_ref` logging), and a per-date
rate calendar on top of rate plans. See PHASES.md's "Out of scope" / "Beyond the numbered
phases" sections.

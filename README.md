<p align="center">
  <img src="static/description/banner.png" alt="Hostel Management for Odoo 19" width="100%"/>
</p>

# Hostel Management

A complete guest-hostel PMS for Odoo 19: multi-property room/bed inventory (private
rooms sold whole, dorms sold bed-by-bed), overlap-safe bookings with locked-in pricing,
check-in/check-out, itemized folios that invoice through standard Odoo Invoicing,
housekeeping, reports, and a set of live front-desk mechanisms (popup notifications,
automatic no-show detection, deposit enforcement, confirmation emails) that a v1.0 feature
list usually leaves for "later."

Built **only** on modules available in Odoo Community (`base`, `mail`, `bus`, `contacts`,
`account`, `product`, `calendar`) — no Enterprise dependency, no Studio, no Documents app,
no third-party Python packages. Installs and behaves identically on Community or
Enterprise.

92 automated tests, 0 failures. License: [OPL-1](LICENSE) (Odoo Proprietary License v1.0) — $100 USD via the Odoo Apps Store.

## Features

- **Multi-property master data** — properties, room types (private room or dorm, bed
  type, amenities, photos), rooms and beds with independent occupancy vs. housekeeping
  status, and rate plans layered on top of a room type's flat default rate. Every
  descriptive/config list (amenities, bed types, sleeping types, ID document types,
  cancellation policies, booking sources, charge types) is an editable model, not a
  hardcoded picklist.
- **Bookings** — whole-room or single-bed, with an overlap constraint that correctly
  blocks a whole-room booking against every bed inside it (and vice versa); price locked
  at booking time so a later rate change never moves an existing booking's price;
  deposits; OTA source/reference tracking; full lifecycle
  (`draft → confirmed → checked_in → checked_out`, plus `cancelled`/`no_show`) with
  check-in/check-out actually driving room/bed status, including the partial-occupancy
  dorm cascade.
- **Folios & billing** — an itemized running bill per stay, auto-opened at check-in with
  its stay line pre-filled; add charges (laundry, food, damage, tours, ...) any time;
  one-click invoicing via standard Odoo Invoicing with no hardcoded tax handling.
  Cancelling or deleting an invoice automatically reopens its folio for re-billing.
- **Housekeeping** — a `checkout_clean` task auto-created on every checkout
  (deduplicated), tracked pending → in progress → done → verified, with a one-click
  "Mark Clean" front-desk shortcut and a live popup the moment a task is assigned to
  someone.
- **Live front-desk mechanisms** — popup notifications (on top of standard chatter
  activities) for arrivals today, checkouts today, and overstays; automatic no-show
  detection that frees a room nobody checked into; deposit enforcement at check-in;
  automatic booking-confirmation emails to the guest; deletion guards so a room, bed, or
  folio with real history can't be silently removed out from under a booking.
- **Reports & dashboards** — QWeb PDFs (booking confirmation, check-in registration
  card, folio, daily arrivals & departures, occupancy/ADR summary), revenue/occupancy
  pivot and graph views, and a status-colored Room Kanban board with front-desk saved
  filters (arrivals today, departures today, in-house now).
- **Security** — property-scoped access for Staff and a separate Housekeeping role
  (unrestricted if no properties are assigned, rather than locked out); Manager is
  always unrestricted; guest ID-document fields are field-level protected.
- **Migration scripts** included, so upgrading an existing install carries old data
  forward cleanly instead of leaving stale values behind.

Deliberately out of scope: POS folio integration, a guest-facing portal, and OTA
channel-manager live sync (only manual `source`/`external_ref` logging) — see
[PHASES.md](PHASES.md)'s "Out of scope" section.

Full decision-by-decision build history (including the bugs each mechanism above
actually caught, not just what shipped) lives in [CLAUDE.md](CLAUDE.md); phase-by-phase
spec in [PHASES.md](PHASES.md); release notes in [CHANGELOG.md](CHANGELOG.md).

## Installation

Drop this folder into any Odoo 19 instance's addons path, update the apps list, and
install **Hostel Management** from Apps (enable Developer Mode first if custom apps
aren't showing).

```
./odoo-bin -c odoo.conf -i hostel_management -d your_database
```

## Development (Docker)

This repo was built against a local Docker Compose stack (Odoo 19 + Postgres) with
`My_Modules/` mounted onto the addons path:

```
docker compose up -d
```

Odoo is then available at http://localhost:8069.

**Installing/upgrading** — don't run this while the `odoo` service is also up on the
same database (`docker compose exec` shares the running container's network namespace
and collides on port 8069); use `docker compose run --rm` instead, which spins up a
separate one-off container:

```
docker compose run --rm odoo python /odoo/odoo-19.0/odoo-bin -c /etc/odoo/odoo.conf \
  -i hostel_management --with-demo -d odoo --test-enable --stop-after-init
```

Swap `-i` for `-u` to upgrade an already-installed module instead of installing fresh.
Watch the output for `N tests ... 0 failed, 0 error(s)` and no traceback — that's a clean
run.

**Note on demo data**: `--with-demo` only actually loads demo data the *first* time a
module is installed (an `-u` upgrade of an already-installed module does not
retroactively load it) — if you need demo data on a database where the module is
already installed without it, drop and recreate the database first, or
uninstall/reinstall the module.

## Getting started (using the demo data)

Install with `--with-demo` (above), then open the **Hostel** app.

1. **Configuration** — browse Properties, Room Types (across two demo properties, each
   with amenities/a sleeping type/a bed type), Rooms, and Beds. Under **Config Lists**
   (Manager only) you'll find the configurable picklists — all editable without
   touching code.
2. **Bookings** — the demo data ships bookings across every state, including an
   OTA-sourced one and a second-property booking using a non-refundable rate plan. Open
   a `draft` one and click through **Confirm → Check In → Check Out** yourself to watch
   room/bed status, the folio, and the live popup notifications update.
3. **Folios** — every checked-in demo booking already has an auto-created folio with
   its stay line. Add an extra charge line and click **Create Invoice** to see a real
   `account.move` generated with no hardcoded tax.
4. **Housekeeping** — a checked-out room leaves behind a pending `checkout_clean` task.
   Assign it to a housekeeping user to see the assignment popup, then walk
   **Start → Done → Verify**, or use the room's own **Mark Clean** shortcut instead.
5. **Reports** — print a booking confirmation, check-in registration card, or folio
   from any relevant record's Print menu. Hostel → Reports → **Occupancy Report** opens
   a date-range wizard; **Revenue & Occupancy** is a pivot/graph on the same data.

## Multi-property access

`hostel.property` supports running more than one location from one database. By
default, **Hostel Staff and Hostel Housekeeping users see every property** — access
only becomes scoped once you explicitly assign properties to a user (Settings → Users
→ open a user → **Access Rights** tab → **Hostel Properties** field). Once a user has
at least one property assigned, they only see that property's rooms/beds/bookings/
folios/housekeeping tasks; **Hostel Manager is never restricted**, regardless of this
field. This fallback (empty = unrestricted, not "restricted to nothing") is deliberate
— see `CLAUDE.md`'s Phase 9 entry for why a naive `in` domain would have silently
locked out every user on a single-property install.

## Security groups

- **Hostel Staff** — front desk: full booking/folio/property/room-type/rate-plan
  access, read-only on the configurable picklists.
- **Hostel Housekeeping** — a separate, independently-assignable track (not a level
  under Staff): read/write on rooms, read-only on beds, full task management, zero
  access to bookings/folios/guest ID documents.
- **Hostel Manager** — implies both of the above, unrestricted by property.

Guest ID document fields (type, number, scan, date of birth) are hidden from general
Odoo users (anyone who can open Contacts but isn't Hostel Staff/Manager) at the view
level — Odoo strips those fields out of the form server-side for unauthorized users,
not just via CSS.

## Testing

```
docker compose run --rm odoo python /odoo/odoo-19.0/odoo-bin -c /etc/odoo/odoo.conf \
  -u hostel_management --with-demo -d odoo --test-enable --test-tags /hostel_management --stop-after-init
```

92 tests across `tests/test_master_data.py`, `test_booking.py`, `test_folio.py`,
`test_housekeeping.py`, `test_reports.py`, and `test_security.py`.

# -*- coding: utf-8 -*-
{
    'name': 'Guesthouse & Hostel Management',
    'version': '19.0.1.0.1',
    'category': 'Services/Hostel',
    'summary': 'Guesthouse & hostel PMS: multi-property rooms/beds, bookings, folios/billing, housekeeping, live front-desk alerts, and reports — Community-only.',
    'description': """
Hostel Management
==================

Standalone guest-hostel PMS built only on Odoo Community modules, so it installs and behaves
identically on Community or Enterprise:

- Multi-property support: room types, rooms, and dorm-style beds scoped per property
- Configurable amenities, bed types, sleeping types, ID document types, cancellation policies,
  booking sources, and charge types - no hardcoded picklists, all editable under Configuration
- Rate plans layered on top of a room type's flat default rate (cancellation policy, min/max stay)
- Guest bookings (whole-room or single-bed) with overlap validation, price-lock pricing, deposits,
  and OTA source/reference tracking
- Check-in / check-out workflow that correctly cascades room and bed occupancy status, including
  partial-occupancy dorms
- Folios: an itemized running bill per stay, auto-opened at check-in with its stay line, extra
  charges added any time, one-click invoicing via standard Odoo Invoicing (no hardcoded tax)
- Housekeeping tasks auto-created on checkout, with a one-click "Mark Clean" front-desk shortcut
  and a live popup the moment a task is assigned to someone
- Live popup notifications for arrivals/checkouts/overstays today, on top of standard chatter
  activities; automatic no-show detection that frees a room nobody checked into; deposit
  enforcement at check-in; automatic booking-confirmation emails to the guest
- Folio/invoice integrity (cancelling or deleting an invoice reopens its folio) and deletion
  guards so a room, bed, or folio with real history can't be silently removed out from under a
  booking
- Room Kanban board, front-desk saved filters (arrivals/departures/in-house), guest stay history
- QWeb PDF reports: booking confirmation, check-in registration card, folio, daily arrivals &
  departures, and an occupancy/ADR summary - plus revenue/occupancy pivot and graph views
- Property-scoped access for Staff/Housekeeping via assigned properties (Managers unrestricted),
  a separate Housekeeping role, and field-level protection on guest ID documents
- Migration scripts included, so upgrading an existing install carries old data forward cleanly
- No Gantt view, no Studio dependency, no Documents app dependency, no POS/portal integration
  (all deliberately out of scope for this build - see PHASES.md)
""",
    'author': 'Hostel Management',
    'license': 'OPL-1',
    'price': 100.00,
    'currency': 'USD',
    'depends': ['base', 'mail', 'bus', 'contacts', 'account', 'product', 'calendar'],
    'data': [
        'security/hostel_security.xml',
        'security/ir.model.access.csv',
        'security/hostel_record_rules.xml',
        'data/hostel_sequence.xml',
        'data/hostel_config_data.xml',
        'data/hostel_cron.xml',
        'data/hostel_mail_templates.xml',
        'views/hostel_property_views.xml',
        'views/hostel_config_views.xml',
        'views/hostel_room_type_views.xml',
        'views/hostel_rate_plan_views.xml',
        'views/hostel_room_views.xml',
        'views/hostel_bed_views.xml',
        'views/hostel_folio_views.xml',
        'views/hostel_housekeeping_task_views.xml',
        'views/hostel_booking_views.xml',
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
        'wizards/hostel_occupancy_report_wizard_views.xml',
        'wizards/hostel_dashboard_views.xml',
        'views/hostel_menus.xml',
        'report/hostel_booking_confirmation_report.xml',
        'report/hostel_checkin_registration_report.xml',
        'report/hostel_folio_report.xml',
        'report/hostel_arrivals_departures_report.xml',
        'report/hostel_occupancy_report.xml',
    ],
    'demo': [
        'demo/phase1_master_data.xml',
        'demo/phase2_bookings.xml',
        'demo/phase3_extended_scope.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'guesthouse_management/static/src/css/brand.css',
            'guesthouse_management/static/src/css/theme.css',
            'guesthouse_management/static/src/css/kanban.css',
            'guesthouse_management/static/src/css/forms.css',
            'guesthouse_management/static/src/css/lists.css',
            'guesthouse_management/static/src/css/dashboard.css',
        ],
    },
    # Banner first (the store list tile), then the screenshots shown on the listing page. The
    # Apps FAQ says the image whose name ends in "_screenshot" is picked as the large display
    # image, hence main_screenshot.png rather than a descriptive name for the dashboard shot.
    'images': [
        'static/description/banner.png',
        'static/description/main_screenshot.png',
        'static/description/workflow.png',
        'static/description/screenshot_bookings.png',
        'static/description/screenshot_rooms_kanban.png',
        'static/description/screenshot_folio.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

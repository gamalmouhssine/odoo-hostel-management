# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class HostelDashboard(models.TransientModel):
    _name = 'hostel.dashboard'
    _description = 'Hostel Dashboard'

    property_id = fields.Many2one(
        'hostel.property', string='Property',
        help="Leave blank to see KPIs across every property.")
    date_from = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self).replace(day=1),
        help="Drives the 'This Period' section and the room-type breakdown below - the "
             "'Right Now' cards and tables are always as of today regardless of this range, "
             "since they're point-in-time front-desk facts, not something a date range "
             "naturally applies to.")
    date_to = fields.Date(required=True, default=lambda self: fields.Date.context_today(self))
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    arrivals_today_count = fields.Integer(string='Arrivals Today')
    departures_today_count = fields.Integer(string='Departures Today')
    in_house_count = fields.Integer(string='In-House Now')
    occupancy_ratio_today = fields.Float(string="Today's Occupancy")
    occupancy_status = fields.Selection([
        ('warning', 'Needs Attention'), ('primary', 'Steady'), ('success', 'Strong'),
    ], string='Occupancy Status')

    pending_housekeeping_count = fields.Integer(string='Housekeeping Tasks Open')
    overdue_invoice_count = fields.Integer(string='Overdue Invoices')

    revenue_period = fields.Monetary(string='Revenue')
    nights_sold_period = fields.Integer(string='Nights Sold')
    adr_period = fields.Monetary(string='ADR')
    occupancy_ratio_period = fields.Float(string='Avg. Occupancy')

    line_ids = fields.One2many('hostel.dashboard.line', 'dashboard_id', string='By Room Type')
    in_house_booking_ids = fields.One2many(
        'hostel.dashboard.booking.line', 'dashboard_id', string='In-House Guests',
        domain=[('kind', '=', 'in_house')])
    upcoming_arrival_ids = fields.One2many(
        'hostel.dashboard.booking.line', 'dashboard_id', string='Upcoming Arrivals',
        domain=[('kind', '=', 'upcoming_arrival')])

    # Refreshed both on creation (so direct ORM use - tests, shell, `env['hostel.dashboard'].
    # create({...})` - gets correct values immediately, matching this model's usual TransientModel
    # wizard convention) and via onchange (so picking a different property/date range in the
    # already-open form recomputes everything live, the standard Odoo pattern for this exact
    # "filter fields drive a bunch of KPIs and a breakdown table" shape - e.g. how a sale order's
    # pricelist onchange recomputes its order lines). A plain `compute=` was tried first and
    # verified correct at the ORM/onchange-RPC layer, but this hybrid is the better-trodden path
    # for a form whose x2many needs to visibly refresh as the user interacts with it, so it's
    # kept in favor of the less common pattern to reduce risk given no browser is available here
    # to confirm live re-rendering directly.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_kpis()
        return records

    @api.onchange('property_id', 'date_from', 'date_to')
    def _onchange_refresh_kpis(self):
        self._refresh_kpis()

    def _refresh_kpis(self):
        for dashboard in self:
            dashboard._refresh_today_kpis()
            dashboard._refresh_period_kpis()

    def _refresh_today_kpis(self):
        self.ensure_one()
        # Bed/booking searches below stay correctly property-scoped for a Staff user even when
        # `properties` includes one they can't see (hostel.property itself has no ir.rule, only
        # a broad ACL) - hostel.room/hostel.booking already carry the real property-scoping
        # ir.rule, and that applies to relational traversal (properties.room_ids) the same as it
        # does to search().
        properties = self.property_id or self.env['hostel.property'].search([])
        self.arrivals_today_count = sum(len(p._get_todays_arrivals()) for p in properties)
        self.departures_today_count = sum(len(p._get_todays_departures()) for p in properties)

        in_house_bookings = self.env['hostel.booking'].search([
            ('property_id', 'in', properties.ids), ('state', '=', 'checked_in'),
        ])
        self.in_house_count = len(in_house_bookings)
        self.in_house_booking_ids = [(5, 0, 0)] + [(0, 0, {
            'kind': 'in_house',
            'booking_id': booking.id,
            'reference_date': booking.check_out_date,
        }) for booking in in_house_bookings]

        today = fields.Date.context_today(self)
        upcoming_bookings = self.env['hostel.booking'].search([
            ('property_id', 'in', properties.ids), ('state', '=', 'confirmed'),
            ('check_in_date', '>=', today), ('check_in_date', '<=', today + timedelta(days=7)),
        ], order='check_in_date')
        self.upcoming_arrival_ids = [(5, 0, 0)] + [(0, 0, {
            'kind': 'upcoming_arrival',
            'booking_id': booking.id,
            'reference_date': booking.check_in_date,
        }) for booking in upcoming_bookings]

        beds = properties.room_ids.bed_ids
        occupied = len(beds.filtered(lambda bed: bed.status == 'occupied'))
        # Stored as a 0-1 ratio, not an already-multiplied percentage - the `percentage` widget
        # multiplies by 100 itself for display (confirmed against formatPercentage() in Odoo's
        # own formatters.js). Storing 50.0 here instead of 0.5 is exactly what produced a real
        # "5000%" bug caught by the client clicking through the actual UI - automated tests
        # never would have caught it since they read the field's raw value directly, not what
        # the widget renders it as.
        self.occupancy_ratio_today = (occupied / len(beds)) if beds else 0.0
        # Unlike every other *_status mapping in this module (which flags a "went wrong" state),
        # high occupancy is the GOOD outcome for a hostel - full beds are revenue, not a problem.
        # Low occupancy is what's worth a staff member's attention.
        if self.occupancy_ratio_today >= 0.7:
            self.occupancy_status = 'success'
        elif self.occupancy_ratio_today >= 0.3:
            self.occupancy_status = 'primary'
        else:
            self.occupancy_status = 'warning'

        self.pending_housekeeping_count = self.env['hostel.housekeeping.task'].search_count([
            ('property_id', 'in', properties.ids), ('state', 'in', ('pending', 'in_progress')),
        ])
        self.overdue_invoice_count = self.env['hostel.folio'].search_count([
            ('property_id', 'in', properties.ids), ('state', '=', 'invoiced'),
            ('invoice_id.payment_state', 'not in', ('paid', 'in_payment', 'reversed')),
            ('invoice_id.invoice_date_due', '<', today),
        ])

    def _refresh_period_kpis(self):
        # Same nights-sold x rate definition of "revenue" as hostel.occupancy.report.wizard's
        # _get_occupancy_lines (booking value for stays overlapping the range), not posted-
        # invoice totals - keeps the top-line KPIs and the per-room-type breakdown below
        # consistent with each other rather than mixing two different notions of "revenue".
        self.ensure_one()
        date_from, date_to = self.date_from, self.date_to
        domain = [
            ('state', 'in', ('checked_in', 'checked_out')),
            ('check_in_date', '<=', date_to),
            ('check_out_date', '>', date_from),
        ]
        if self.property_id:
            domain.append(('property_id', '=', self.property_id.id))
        bookings = self.env['hostel.booking'].search(domain)
        total_days = (date_to - date_from).days + 1 if date_to and date_from else 0

        total_nights, total_revenue, total_available = 0, 0.0, 0
        line_commands = [(5, 0, 0)]
        for room_type in bookings.room_type_id:
            rt_bookings = bookings.filtered(lambda b: b.room_type_id == room_type)
            nights_sold, revenue = 0, 0.0
            for booking in rt_bookings:
                overlap_start = max(booking.check_in_date, date_from)
                overlap_end = min(booking.check_out_date, date_to + timedelta(days=1))
                overlap_nights = max((overlap_end - overlap_start).days, 0)
                nights_sold += overlap_nights
                revenue += overlap_nights * booking.rate
            room_count = self.env['hostel.room'].search_count([('room_type_id', '=', room_type.id)])
            available_room_nights = room_count * total_days
            total_nights += nights_sold
            total_revenue += revenue
            total_available += available_room_nights
            line_commands.append((0, 0, {
                'room_type_id': room_type.id,
                'nights_sold': nights_sold,
                'available_room_nights': available_room_nights,
                'occupancy_ratio': (nights_sold / available_room_nights) if available_room_nights else 0.0,
                'revenue': revenue,
                'adr': (revenue / nights_sold) if nights_sold else 0.0,
            }))
        self.line_ids = line_commands
        self.revenue_period = total_revenue
        self.nights_sold_period = total_nights
        self.adr_period = (total_revenue / total_nights) if total_nights else 0.0
        self.occupancy_ratio_period = (total_nights / total_available) if total_available else 0.0


class HostelDashboardLine(models.TransientModel):
    _name = 'hostel.dashboard.line'
    _description = 'Hostel Dashboard Room Type Breakdown'

    dashboard_id = fields.Many2one('hostel.dashboard', required=True, ondelete='cascade')
    room_type_id = fields.Many2one('hostel.room.type', required=True)
    nights_sold = fields.Integer()
    available_room_nights = fields.Integer()
    occupancy_ratio = fields.Float(string='Occupancy')
    revenue = fields.Monetary()
    adr = fields.Monetary(string='ADR')
    currency_id = fields.Many2one(related='dashboard_id.currency_id')


class HostelDashboardBookingLine(models.TransientModel):
    _name = 'hostel.dashboard.booking.line'
    _description = 'Hostel Dashboard Booking Row (in-house / upcoming arrival)'

    dashboard_id = fields.Many2one('hostel.dashboard', required=True, ondelete='cascade')
    kind = fields.Selection([
        ('in_house', 'In-House'), ('upcoming_arrival', 'Upcoming Arrival'),
    ], required=True)
    booking_id = fields.Many2one('hostel.booking', required=True, ondelete='cascade')
    reference_date = fields.Date(
        string='Date', help="Checkout date for an in-house row, check-in date for an "
                             "upcoming-arrival row - whichever date is the relevant one to "
                             "show depends on which list this row belongs to.")
    guest_id = fields.Many2one(related='booking_id.guest_id')
    room_display_name = fields.Char(compute='_compute_room_display_name')

    @api.depends('booking_id.room_id', 'booking_id.bed_id')
    def _compute_room_display_name(self):
        for line in self:
            booking = line.booking_id
            line.room_display_name = (
                booking.bed_id.display_name if booking.booking_unit == 'bed'
                else booking.room_id.display_name)

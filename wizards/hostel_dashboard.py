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
             "'Right Now' cards (arrivals/departures/in-house/today's occupancy) are always "
             "as of today regardless of this range, since they're point-in-time front-desk "
             "facts, not something a date range naturally applies to.")
    date_to = fields.Date(required=True, default=lambda self: fields.Date.context_today(self))
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')

    arrivals_today_count = fields.Integer(compute='_compute_today_kpis', string='Arrivals Today')
    departures_today_count = fields.Integer(compute='_compute_today_kpis', string='Departures Today')
    in_house_count = fields.Integer(compute='_compute_today_kpis', string='In-House Now')
    occupancy_ratio_today = fields.Float(compute='_compute_today_kpis', string="Today's Occupancy")
    occupancy_status = fields.Selection([
        ('warning', 'Needs Attention'), ('primary', 'Steady'), ('success', 'Strong'),
    ], compute='_compute_today_kpis', string='Occupancy Status')

    revenue_period = fields.Monetary(compute='_compute_period_kpis', string='Revenue')
    nights_sold_period = fields.Integer(compute='_compute_period_kpis', string='Nights Sold')
    adr_period = fields.Monetary(compute='_compute_period_kpis', string='ADR')
    occupancy_ratio_period = fields.Float(compute='_compute_period_kpis', string='Avg. Occupancy')
    line_ids = fields.One2many(
        'hostel.dashboard.line', 'dashboard_id', compute='_compute_period_kpis',
        string='By Room Type')

    def _compute_currency_id(self):
        currency = self.env.company.currency_id
        for dashboard in self:
            dashboard.currency_id = currency

    @api.depends('property_id')
    def _compute_today_kpis(self):
        # Bed/booking searches below stay correctly property-scoped for a Staff user even when
        # `properties` includes one they can't see (hostel.property itself has no ir.rule, only
        # a broad ACL) - hostel.room/hostel.booking already carry the real property-scoping
        # ir.rule, and that applies to relational traversal (properties.room_ids) the same as it
        # does to search().
        for dashboard in self:
            properties = dashboard.property_id or self.env['hostel.property'].search([])
            dashboard.arrivals_today_count = sum(len(p._get_todays_arrivals()) for p in properties)
            dashboard.departures_today_count = sum(len(p._get_todays_departures()) for p in properties)
            dashboard.in_house_count = self.env['hostel.booking'].search_count([
                ('property_id', 'in', properties.ids), ('state', '=', 'checked_in'),
            ])
            beds = properties.room_ids.bed_ids
            occupied = len(beds.filtered(lambda bed: bed.status == 'occupied'))
            # Stored as a 0-1 ratio, not an already-multiplied percentage - the `percentage`
            # widget multiplies by 100 itself for display (confirmed against formatPercentage()
            # in Odoo's own formatters.js). Storing 50.0 here instead of 0.5 is exactly what
            # produced a real "5000%" bug caught by the client clicking through the actual UI -
            # automated tests never would have caught it since they read the field's raw value
            # directly, not what the widget renders it as.
            dashboard.occupancy_ratio_today = (occupied / len(beds)) if beds else 0.0
            # Unlike every other *_color/*_status mapping in this module (which flags a "went
            # wrong" state), high occupancy is the GOOD outcome for a hostel - full beds are
            # revenue, not a problem. Low occupancy is what's worth a staff member's attention.
            if dashboard.occupancy_ratio_today >= 0.7:
                dashboard.occupancy_status = 'success'
            elif dashboard.occupancy_ratio_today >= 0.3:
                dashboard.occupancy_status = 'primary'
            else:
                dashboard.occupancy_status = 'warning'

    @api.depends('property_id', 'date_from', 'date_to')
    def _compute_period_kpis(self):
        # Same nights-sold x rate definition of "revenue" as hostel.occupancy.report.wizard's
        # _get_occupancy_lines (booking value for stays overlapping the range), not posted-
        # invoice totals - keeps the top-line KPIs and the per-room-type breakdown below
        # consistent with each other rather than mixing two different notions of "revenue".
        for dashboard in self:
            date_from, date_to = dashboard.date_from, dashboard.date_to
            domain = [
                ('state', 'in', ('checked_in', 'checked_out')),
                ('check_in_date', '<=', date_to),
                ('check_out_date', '>', date_from),
            ]
            if dashboard.property_id:
                domain.append(('property_id', '=', dashboard.property_id.id))
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
            dashboard.line_ids = line_commands
            dashboard.revenue_period = total_revenue
            dashboard.nights_sold_period = total_nights
            dashboard.adr_period = (total_revenue / total_nights) if total_nights else 0.0
            dashboard.occupancy_ratio_period = (total_nights / total_available) if total_available else 0.0


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

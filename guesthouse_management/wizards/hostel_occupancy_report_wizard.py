# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class HostelOccupancyReportWizard(models.TransientModel):
    _name = 'hostel.occupancy.report.wizard'
    _description = 'Hostel Occupancy Report Wizard'

    date_from = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(required=True, default=lambda self: fields.Date.context_today(self))
    property_id = fields.Many2one('hostel.property')

    def action_print_report(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError("The end date must be on or after the start date.")
        return self.env.ref('guesthouse_management.action_report_hostel_occupancy').report_action(self)

    def _get_occupancy_lines(self):
        """One aggregate row per room type that had any qualifying booking in range: nights
        sold vs. available room-nights (room_count * days in range), occupancy %, revenue, and
        ADR (Average Daily Rate = revenue / nights sold). Only counts the portion of each
        booking's nights that actually falls inside [date_from, date_to]."""
        self.ensure_one()
        domain = [
            ('state', 'in', ('checked_in', 'checked_out')),
            ('check_in_date', '<=', self.date_to),
            ('check_out_date', '>', self.date_from),
        ]
        if self.property_id:
            domain.append(('property_id', '=', self.property_id.id))
        bookings = self.env['hostel.booking'].search(domain)
        total_days = (self.date_to - self.date_from).days + 1
        lines = []
        for room_type in bookings.room_type_id:
            rt_bookings = bookings.filtered(lambda b: b.room_type_id == room_type)
            nights_sold = 0
            revenue = 0.0
            for booking in rt_bookings:
                overlap_start = max(booking.check_in_date, self.date_from)
                overlap_end = min(booking.check_out_date, self.date_to + timedelta(days=1))
                overlap_nights = max((overlap_end - overlap_start).days, 0)
                nights_sold += overlap_nights
                revenue += overlap_nights * booking.rate
            room_count = self.env['hostel.room'].search_count([('room_type_id', '=', room_type.id)])
            available_room_nights = room_count * total_days
            lines.append({
                'room_type': room_type,
                'nights_sold': nights_sold,
                'available_room_nights': available_room_nights,
                'occupancy_pct': (nights_sold / available_room_nights * 100.0) if available_room_nights else 0.0,
                'revenue': revenue,
                'adr': (revenue / nights_sold) if nights_sold else 0.0,
            })
        return lines

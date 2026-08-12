# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError

BED_STATUS_SELECTION = [
    ('available', 'Available'),
    ('booked', 'Booked'),
    ('occupied', 'Occupied'),
    ('maintenance', 'Maintenance'),
]


class HostelBed(models.Model):
    _name = 'hostel.bed'
    _description = 'Hostel Bed'
    _inherit = ['mail.thread']
    _order = 'room_id, name'

    name = fields.Char(string='Bed Code', required=True, tracking=True)
    room_id = fields.Many2one('hostel.room', required=True, ondelete='cascade', tracking=True)
    status = fields.Selection(BED_STATUS_SELECTION, default='available', required=True, tracking=True)
    is_female_only = fields.Boolean(string='Female Only')
    is_bottom_bunk = fields.Boolean(string='Bottom Bunk')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(related='room_id.company_id', store=True, string='Company')

    _name_room_uniq = models.Constraint(
        'unique(name, room_id)',
        'Bed code must be unique within a room.',
    )

    def unlink(self):
        bookings = self.env['hostel.booking'].search([('bed_id', 'in', self.ids)], limit=1)
        if bookings:
            raise UserError(
                "Cannot delete a bed that has booking history (e.g. %s) — the booking's bed_id "
                "would silently go blank. Archive it instead (Active = No)." % bookings.name)
        return super().unlink()

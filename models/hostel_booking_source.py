# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelBookingSource(models.Model):
    _name = 'hostel.booking.source'
    _description = 'Hostel Booking Source'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    is_ota = fields.Boolean(
        string='Is OTA', help="Online Travel Agency (Booking.com, Hostelworld, etc.) — "
                               "bookings from an OTA source are expected to carry an external_ref.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'A booking source with this name already exists.',
    )

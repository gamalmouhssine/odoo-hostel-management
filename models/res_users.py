# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    hostel_property_ids = fields.Many2many(
        'hostel.property', string='Hostel Properties',
        help="Restricts Hostel Staff/Housekeeping users to these properties' rooms, beds, "
             "bookings, folios, and housekeeping tasks. Leave empty to see all properties "
             "(the default, safe for single-property installs) - Hostel Managers are never "
             "restricted regardless of this field.")

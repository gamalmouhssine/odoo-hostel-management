# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelAmenity(models.Model):
    _name = 'hostel.amenity'
    _description = 'Hostel Room Amenity'
    _order = 'name'

    name = fields.Char(required=True)
    icon = fields.Char(help="Optional FontAwesome class, e.g. 'fa-wifi'.")
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'An amenity with this name already exists.',
    )

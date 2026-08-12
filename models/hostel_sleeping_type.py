# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelSleepingType(models.Model):
    _name = 'hostel.sleeping.type'
    _description = 'Hostel Room Sleeping Type'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'A sleeping type with this name already exists.',
    )

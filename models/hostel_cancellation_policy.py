# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelCancellationPolicy(models.Model):
    _name = 'hostel.cancellation.policy'
    _description = 'Hostel Rate Plan Cancellation Policy'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'A cancellation policy with this name already exists.',
    )

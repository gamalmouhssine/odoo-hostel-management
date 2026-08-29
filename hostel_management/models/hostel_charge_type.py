# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelChargeType(models.Model):
    _name = 'hostel.charge.type'
    _description = 'Hostel Folio Charge Type'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    is_stay = fields.Boolean(
        string='Is Stay Charge',
        help="Marks the charge type used for the auto-generated nightly-stay line. Informational "
             "only - not enforced - but keep exactly one active record flagged this way, since "
             "check-in looks it up by the hostel_management.hostel_charge_type_stay XML ID.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'A charge type with this name already exists.',
    )

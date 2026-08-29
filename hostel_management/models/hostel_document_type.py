# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelDocumentType(models.Model):
    _name = 'hostel.document.type'
    _description = 'Hostel Guest ID Document Type'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'A document type with this name already exists.',
    )

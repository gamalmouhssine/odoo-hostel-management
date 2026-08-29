# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelHousekeepingTaskType(models.Model):
    _name = 'hostel.housekeeping.task.type'
    _description = 'Hostel Housekeeping Task Type'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    is_checkout_clean = fields.Boolean(
        string='Is Checkout Clean',
        help="Marks the task type auto-created on checkout. Informational only - not enforced - "
             "but keep exactly one active record flagged this way, since checkout looks it up by "
             "the guesthouse_management.hostel_housekeeping_task_type_checkout_clean XML ID.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'A housekeeping task type with this name already exists.',
    )

# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelRatePlan(models.Model):
    _name = 'hostel.rate_plan'
    _description = 'Hostel Rate Plan'
    _order = 'room_type_id, name'

    name = fields.Char(required=True)
    room_type_id = fields.Many2one('hostel.room.type', string='Room Type', required=True, ondelete='cascade')
    price_per_night = fields.Monetary(required=True)
    company_id = fields.Many2one(related='room_type_id.company_id', store=True, string='Company')
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency', readonly=True)
    cancellation_policy_id = fields.Many2one(
        'hostel.cancellation.policy', string='Cancellation Policy', required=True,
        default=lambda self: self.env.ref(
            'guesthouse_management.hostel_cancellation_policy_flexible', raise_if_not_found=False))
    min_stay_nights = fields.Integer(default=1)
    max_stay_nights = fields.Integer(help="0 means no maximum.")
    active = fields.Boolean(default=True)

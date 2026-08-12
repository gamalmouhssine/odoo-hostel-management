# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.addons.base.models.res_partner import _tz_get


class HostelProperty(models.Model):
    _name = 'hostel.property'
    _description = 'Hostel Property'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state', string='State')
    zip = fields.Char(string='ZIP')
    country_id = fields.Many2one('res.country')
    timezone = fields.Selection(_tz_get, string='Timezone')
    check_in_time = fields.Float(string='Check-in Time', default=14.0)
    check_out_time = fields.Float(string='Check-out Time', default=11.0)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    room_type_ids = fields.One2many('hostel.room.type', 'property_id', string='Room Types')
    room_ids = fields.One2many('hostel.room', 'property_id', string='Rooms')
    room_count = fields.Integer(compute='_compute_room_bed_count')
    bed_count = fields.Integer(compute='_compute_room_bed_count')
    today_occupancy_rate = fields.Float(
        compute='_compute_today_occupancy_rate', string="Today's Occupancy %")

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'Property code must be unique per company.',
    )

    @api.depends('room_ids', 'room_ids.bed_ids')
    def _compute_room_bed_count(self):
        for prop in self:
            prop.room_count = len(prop.room_ids)
            prop.bed_count = len(prop.room_ids.bed_ids)

    def _compute_today_occupancy_rate(self):
        for prop in self:
            beds = prop.room_ids.bed_ids
            occupied = len(beds.filtered(lambda bed: bed.status == 'occupied'))
            prop.today_occupancy_rate = (occupied / len(beds) * 100.0) if beds else 0.0

    def _get_todays_arrivals(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        return self.env['hostel.booking'].search([
            ('property_id', '=', self.id),
            ('check_in_date', '=', today),
            ('state', '=', 'confirmed'),
        ])

    def _get_todays_departures(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        return self.env['hostel.booking'].search([
            ('property_id', '=', self.id),
            ('check_out_date', '=', today),
            ('state', '=', 'checked_in'),
        ])

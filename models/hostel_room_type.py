# -*- coding: utf-8 -*-
from odoo import fields, models


class HostelRoomType(models.Model):
    _name = 'hostel.room.type'
    _description = 'Hostel Room Type'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    property_id = fields.Many2one('hostel.property', string='Property', required=True)
    sleeping_type_id = fields.Many2one(
        'hostel.sleeping.type', string='Sleeping Type', required=True,
        default=lambda self: self.env.ref(
            'hostel_management.hostel_sleeping_type_dorm', raise_if_not_found=False))
    bed_type_id = fields.Many2one('hostel.bed.type', string='Bed Type')
    amenity_ids = fields.Many2many('hostel.amenity', string='Amenities')
    photo_ids = fields.Many2many(
        'ir.attachment', 'hostel_room_type_photo_rel', 'room_type_id', 'attachment_id',
        string='Photos', domain=[('mimetype', 'like', 'image')])
    default_rate = fields.Monetary(
        string='Default Nightly Rate',
        help="Flat fallback rate used when the room type has no default_rate_id rate plan set.")
    default_rate_id = fields.Many2one(
        'hostel.rate_plan', string='Default Rate Plan',
        domain="[('room_type_id', '=', id)]",
        help="Optional. When set, bookings snapshot their rate from this plan instead of the "
             "flat Default Nightly Rate above.")
    rate_plan_ids = fields.One2many('hostel.rate_plan', 'room_type_id', string='Rate Plans')
    capacity = fields.Integer(string='Default Capacity', default=1)
    description = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency', readonly=True)

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'Room type code must be unique per company.',
    )

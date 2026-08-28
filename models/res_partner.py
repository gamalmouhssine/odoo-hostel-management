# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_hostel_guest = fields.Boolean(string='Hostel Guest')
    id_document_type_id = fields.Many2one('hostel.document.type', string='ID Document Type')
    id_document_number = fields.Char(string='ID Document Number')
    id_document = fields.Binary(string='ID Document Scan', attachment=True)
    id_document_filename = fields.Char(string='ID Document Filename')
    date_of_birth = fields.Date()
    nationality_id = fields.Many2one('res.country', string='Nationality')
    emergency_contact_name = fields.Char(string='Emergency Contact Name')
    emergency_contact_phone = fields.Char(string='Emergency Contact Phone')
    is_blacklisted = fields.Boolean(
        string='Blacklisted',
        help="Blocks confirming any new booking for this guest (e.g. past damage, unpaid bill, "
             "no-show pattern). Existing draft bookings are left alone so staff can still "
             "discuss the situation with a manager before deciding - the block is on "
             "confirming, not on drafting.")
    blacklist_reason = fields.Text()

    booking_ids = fields.One2many('hostel.booking', 'guest_id', string='Bookings')
    currency_id = fields.Many2one('res.currency', compute='_compute_hostel_currency_id')
    stay_count = fields.Integer(string='Stays', compute='_compute_hostel_stats')
    total_nights = fields.Integer(compute='_compute_hostel_stats')
    total_spend = fields.Monetary(compute='_compute_hostel_stats', currency_field='currency_id')

    def _compute_hostel_currency_id(self):
        currency = self.env.company.currency_id
        for partner in self:
            partner.currency_id = currency

    @api.depends('booking_ids.state', 'booking_ids.nights', 'booking_ids.total_price')
    def _compute_hostel_stats(self):
        # Bookings that actually happened (or are happening) count toward guest history;
        # draft/confirmed/cancelled/no_show do not. Guard against unsaved (NewId) partners,
        # e.g. while filling in a quick-create form, which have nothing to search for yet.
        saved_partners = self.filtered('id')
        bookings_by_guest = self.env['hostel.booking']._read_group(
            [('guest_id', 'in', saved_partners.ids), ('state', 'in', ('checked_in', 'checked_out'))],
            groupby=['guest_id'],
            aggregates=['__count', 'nights:sum', 'total_price:sum'],
        ) if saved_partners else []
        stats = {
            guest.id: (count, nights, total)
            for guest, count, nights, total in bookings_by_guest
        }
        for partner in self:
            count, nights, total = stats.get(partner.id, (0, 0, 0.0))
            partner.stay_count = count
            partner.total_nights = nights
            partner.total_spend = total

    def action_view_hostel_bookings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bookings',
            'res_model': 'hostel.booking',
            'view_mode': 'list,form,calendar',
            'domain': [('guest_id', '=', self.id)],
            'context': {'default_guest_id': self.id},
        }

# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    hostel_folio_id = fields.Many2one('hostel.folio', string='Hostel Folio', copy=False)
    hostel_booking_id = fields.Many2one(related='hostel_folio_id.booking_id', string='Hostel Booking')

    def button_cancel(self):
        result = super().button_cancel()
        folios = self.hostel_folio_id.filtered(lambda f: f.state == 'invoiced')
        if folios:
            folios.write({'invoice_id': False, 'state': 'open'})
        return result

    def unlink(self):
        folios = self.env['hostel.folio'].search([('invoice_id', 'in', self.ids)])
        result = super().unlink()
        if folios:
            folios.write({'invoice_id': False, 'state': 'open'})
        return result

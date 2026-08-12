# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HostelFolioLine(models.Model):
    _name = 'hostel.folio.line'
    _description = 'Hostel Folio Line'
    _order = 'folio_id, id'

    folio_id = fields.Many2one('hostel.folio', required=True, ondelete='cascade', index=True)
    charge_type_id = fields.Many2one('hostel.charge.type', string='Charge Type')
    product_id = fields.Many2one('product.product', string='Product')
    description = fields.Char(required=True)
    qty = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Monetary()
    subtotal = fields.Monetary(compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one(related='folio_id.currency_id')
    folio_state = fields.Selection(related='folio_id.state', string='Folio Status')

    @api.depends('qty', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.unit_price = self.product_id.lst_price

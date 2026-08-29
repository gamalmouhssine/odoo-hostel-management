# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class HostelFolio(models.Model):
    _name = 'hostel.folio'
    _description = 'Hostel Folio'
    _inherit = ['mail.thread']
    _order = 'id desc'

    booking_id = fields.Many2one('hostel.booking', required=True, ondelete='cascade', index=True)
    guest_id = fields.Many2one(related='booking_id.guest_id', store=True)
    property_id = fields.Many2one(related='booking_id.property_id', store=True)
    company_id = fields.Many2one(related='booking_id.company_id', store=True)
    currency_id = fields.Many2one(related='booking_id.currency_id')
    line_ids = fields.One2many('hostel.folio.line', 'folio_id', string='Lines')
    amount_total = fields.Monetary(compute='_compute_amount_total', store=True)
    state = fields.Selection([
        ('open', 'Open'),
        ('invoiced', 'Invoiced'),
    ], default='open', required=True, tracking=True,
        help="Open: still being billed, lines editable. Invoiced: an account.move exists for "
             "this folio - whether it's actually been paid is payment_state, a live related "
             "field off the invoice itself, not a second state tracked here (nothing on this "
             "model's own side could keep a duplicate 'paid' value reliably in sync with "
             "payment reconciliation, which updates account.move.payment_state via the ORM's "
             "internal recompute path, not a plain write() this model could hook).")
    invoice_id = fields.Many2one('account.move', readonly=True, copy=False)
    payment_state = fields.Selection(related='invoice_id.payment_state', readonly=True)
    payment_reminder_notified = fields.Boolean(
        default=False, copy=False,
        help="Set once _cron_overdue_invoice_reminders has already popped a reminder for this "
             "folio's invoice, so it fires once per invoice, not on every cron run. Reset "
             "whenever a fresh invoice is created - a new invoice means a new due date, so "
             "fresh eligibility.")

    @api.depends('line_ids.subtotal')
    def _compute_amount_total(self):
        for folio in self:
            folio.amount_total = sum(folio.line_ids.mapped('subtotal'))

    def action_create_invoice(self):
        self.ensure_one()
        if self.state != 'open':
            raise UserError("This folio has already been invoiced.")
        if not self.line_ids:
            raise UserError("Cannot invoice an empty folio.")
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.guest_id.id,
            'invoice_origin': self.booking_id.name,
            'hostel_folio_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'name': line.description,
                'quantity': line.qty,
                'price_unit': line.unit_price,
            }) for line in self.line_ids],
        })
        self.write({'invoice_id': move.id, 'state': 'invoiced', 'payment_reminder_notified': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def unlink(self):
        if any(folio.state == 'invoiced' for folio in self):
            raise UserError(
                "Cannot delete an invoiced folio. Cancel or delete its invoice first "
                "(that automatically reopens the folio for editing/re-invoicing).")
        return super().unlink()

    @api.model
    def _cron_overdue_invoice_reminders(self):
        """The billing-side counterpart to hostel.booking's four reminder crons: those all
        close a loop on the booking lifecycle, nothing closed one on the invoice actually
        getting paid. Reuses account.move's own accounting semantics for "overdue"
        (invoice_date_due passed, payment_state not settled) rather than inventing a custom
        day-count, and the same _notifiable_property_users helper/simple_notification bus
        mechanism as the booking crons - that helper only reads .property_id off whatever's
        passed in, and hostel.folio has its own (related, stored) property_id, so no booking_id
        indirection needed."""
        today = fields.Date.context_today(self)
        folios = self.search([
            ('state', '=', 'invoiced'),
            ('payment_reminder_notified', '=', False),
            ('invoice_id.payment_state', 'not in', ('paid', 'in_payment', 'reversed')),
            ('invoice_id.invoice_date_due', '<', today),
        ])
        Booking = self.env['hostel.booking']
        for folio in folios:
            Booking._notifiable_property_users(folio)._bus_send('simple_notification', {
                'type': 'danger',
                'title': 'Overdue Invoice',
                'message': '%s: invoice %s for %s is overdue and still not paid.' % (
                    folio.booking_id.name, folio.invoice_id.name or folio.invoice_id.display_name,
                    folio.guest_id.name),
                'sticky': True,
            })
        folios.write({'payment_reminder_notified': True})

    def action_view_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

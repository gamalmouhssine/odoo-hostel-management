# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HostelDashboard(models.TransientModel):
    _name = 'hostel.dashboard'
    _description = 'Hostel Dashboard'

    property_id = fields.Many2one(
        'hostel.property', string='Property',
        help="Leave blank to see KPIs across every property.")
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    arrivals_today_count = fields.Integer(compute='_compute_kpis', string='Arrivals Today')
    departures_today_count = fields.Integer(compute='_compute_kpis', string='Departures Today')
    in_house_count = fields.Integer(compute='_compute_kpis', string='In-House Now')
    occupancy_pct_today = fields.Float(compute='_compute_kpis', string="Today's Occupancy")
    revenue_mtd = fields.Monetary(compute='_compute_kpis', string='Revenue This Month')
    occupancy_status = fields.Selection([
        ('warning', 'Needs Attention'), ('primary', 'Steady'), ('success', 'Strong'),
    ], compute='_compute_kpis', string='Occupancy Status')

    def _compute_currency_id(self):
        currency = self.env.company.currency_id
        for dashboard in self:
            dashboard.currency_id = currency

    @api.depends('property_id')
    def _compute_kpis(self):
        # Bed/booking/invoice searches below stay correctly property-scoped for a Staff user
        # even when `properties` includes one they can't see (hostel.property itself has no
        # ir.rule, only a broad ACL) - hostel.room/hostel.booking/account.move (via
        # hostel_folio_id) all carry the real property-scoping ir.rule already, and that applies
        # to relational traversal (properties.room_ids etc.) the same as it does to search().
        for dashboard in self:
            properties = dashboard.property_id or self.env['hostel.property'].search([])
            dashboard.arrivals_today_count = sum(len(p._get_todays_arrivals()) for p in properties)
            dashboard.departures_today_count = sum(len(p._get_todays_departures()) for p in properties)
            dashboard.in_house_count = self.env['hostel.booking'].search_count([
                ('property_id', 'in', properties.ids), ('state', '=', 'checked_in'),
            ])
            beds = properties.room_ids.bed_ids
            occupied = len(beds.filtered(lambda bed: bed.status == 'occupied'))
            dashboard.occupancy_pct_today = (occupied / len(beds) * 100.0) if beds else 0.0
            today = fields.Date.context_today(dashboard)
            invoices = self.env['account.move'].search([
                ('hostel_folio_id.property_id', 'in', properties.ids),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', today.replace(day=1)),
                ('invoice_date', '<=', today),
            ])
            dashboard.revenue_mtd = sum(invoices.mapped('amount_total'))
            # Unlike every other *_color mapping in this module (which colors a "did something
            # go wrong" state), high occupancy is the GOOD outcome for a hostel - full beds are
            # revenue, not a problem. So the scale runs the opposite way: low occupancy is the
            # thing worth a staff member's attention (empty beds, maybe needs a marketing push),
            # not high occupancy.
            if dashboard.occupancy_pct_today >= 70:
                dashboard.occupancy_status = 'success'
            elif dashboard.occupancy_pct_today >= 30:
                dashboard.occupancy_status = 'primary'
            else:
                dashboard.occupancy_status = 'warning'

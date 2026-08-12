# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

ROOM_STATE_SELECTION = [
    ('available', 'Available'),
    ('occupied', 'Occupied'),
    ('maintenance', 'Maintenance'),
    ('out_of_order', 'Out of Order'),
]

HOUSEKEEPING_STATUS_SELECTION = [
    ('clean', 'Clean'),
    ('dirty', 'Dirty'),
    ('inspected', 'Inspected'),
    ('do_not_disturb', 'Do Not Disturb'),
]

# Pill color per value, per kanban.css's documented mapping - reused everywhere a status shows
# as a colored badge (Room Kanban, list decorations). Keep this in sync with kanban.css by hand;
# there's no single source of truth shared between Python and CSS in stock Odoo.
STATE_COLOR = {
    'available': 'success', 'occupied': 'primary',
    'maintenance': 'destructive', 'out_of_order': 'destructive',
}
HOUSEKEEPING_STATUS_COLOR = {
    'clean': 'success', 'dirty': 'warning', 'inspected': 'primary', 'do_not_disturb': 'secondary',
}


class HostelRoom(models.Model):
    _name = 'hostel.room'
    _description = 'Hostel Room'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(string='Room Number', required=True, tracking=True)
    floor = fields.Char()
    room_type_id = fields.Many2one('hostel.room.type', string='Room Type', required=True, tracking=True)
    property_id = fields.Many2one(
        'hostel.property', related='room_type_id.property_id', store=True, string='Property')
    capacity = fields.Integer(compute='_compute_capacity', store=True, readonly=False)
    state = fields.Selection(
        ROOM_STATE_SELECTION, default='available', required=True, tracking=True,
        help="Occupancy/availability axis, independent of housekeeping_status — a room can be "
             "occupied and dirty at the same time.")
    housekeeping_status = fields.Selection(
        HOUSEKEEPING_STATUS_SELECTION, default='clean', required=True, tracking=True)
    bed_ids = fields.One2many('hostel.bed', 'room_id', string='Beds')
    housekeeping_task_ids = fields.One2many('hostel.housekeeping.task', 'room_id', string='Housekeeping Tasks')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state_color = fields.Char(compute='_compute_state_color')
    housekeeping_status_color = fields.Char(compute='_compute_state_color')

    @api.depends('room_type_id')
    def _compute_capacity(self):
        for room in self:
            room.capacity = room.room_type_id.capacity or 1

    @api.depends('state', 'housekeeping_status')
    def _compute_state_color(self):
        for room in self:
            room.state_color = STATE_COLOR.get(room.state, 'secondary')
            room.housekeeping_status_color = HOUSEKEEPING_STATUS_COLOR.get(room.housekeeping_status, 'secondary')

    def unlink(self):
        # Check bed-level booking history too, not just room-level: hostel.bed.room_id has
        # ondelete='cascade', which Odoo implements as a raw SQL FK constraint, NOT by calling
        # hostel.bed's own unlink() override - so deleting a room would silently bypass that
        # guard and cascade-delete beds with real booking history behind them if this method
        # only checked its own room_id bookings. Confirmed by a test that caught exactly this
        # before this line existed.
        bookings = self.env['hostel.booking'].search([
            '|', ('room_id', 'in', self.ids), ('bed_id.room_id', 'in', self.ids),
        ], limit=1)
        if bookings:
            raise UserError(
                "Cannot delete a room that has booking history (e.g. %s), including via its "
                "beds — the booking's room_id/bed_id would silently go blank. Archive it "
                "instead (Active = No)." % bookings.name)
        return super().unlink()

    def _create_checkout_task(self):
        """Create a pending checkout_clean housekeeping task for this room, unless one is
        already open (e.g. a prior checkout on the same room whose task hasn't been completed
        yet - don't pile up duplicates for the same cleaning job)."""
        self.ensure_one()
        existing = self.env['hostel.housekeeping.task'].search([
            ('room_id', '=', self.id),
            ('state', 'not in', ('done', 'verified')),
        ], limit=1)
        if existing:
            return existing
        checkout_clean_type = self.env.ref(
            'hostel_management.hostel_housekeeping_task_type_checkout_clean', raise_if_not_found=False)
        return self.env['hostel.housekeeping.task'].create({
            'room_id': self.id,
            'type_id': checkout_clean_type.id if checkout_clean_type else False,
        })

    def action_mark_clean(self):
        """One-click front-desk shortcut: clears housekeeping_status and completes whichever
        open housekeeping task prompted the cleaning (if any) - keeps the quick-action path and
        the tracked-task path in sync rather than being two disconnected mechanisms."""
        open_tasks = self.env['hostel.housekeeping.task'].search([
            ('room_id', 'in', self.ids),
            ('state', 'not in', ('done', 'verified')),
        ])
        open_tasks.action_done()
        self.write({'housekeeping_status': 'clean'})

    def _sync_state_from_beds(self):
        """Recompute a room's occupied/available state from its beds' statuses: occupied only
        once ALL beds are occupied (a dorm with free beds is still bookable/available), else
        available. Only touches the available/occupied axis - a room manually set to
        maintenance/out_of_order is left alone, since that's a deliberate override, not a
        booking-driven fact."""
        for room in self:
            if room.state not in ('available', 'occupied'):
                continue
            beds = room.bed_ids
            room.state = 'occupied' if beds and all(bed.status == 'occupied' for bed in beds) else 'available'

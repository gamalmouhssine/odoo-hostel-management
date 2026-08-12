# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HostelHousekeepingTask(models.Model):
    _name = 'hostel.housekeeping.task'
    _description = 'Hostel Housekeeping Task'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    room_id = fields.Many2one('hostel.room', required=True, tracking=True, index=True)
    property_id = fields.Many2one(related='room_id.property_id', store=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    type_id = fields.Many2one('hostel.housekeeping.task.type', string='Type', required=True)
    assigned_to_id = fields.Many2one('res.users', string='Assigned To', tracking=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('verified', 'Verified'),
    ], default='pending', required=True, tracking=True)
    notes = fields.Text()
    company_id = fields.Many2one(related='room_id.company_id', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        for task in tasks:
            if task.assigned_to_id:
                task._notify_assignment()
        return tasks

    def write(self, vals):
        previous_assignee_ids = {}
        if 'assigned_to_id' in vals:
            previous_assignee_ids = {task.id: task.assigned_to_id.id for task in self}
        result = super().write(vals)
        if 'assigned_to_id' in vals:
            for task in self:
                if task.assigned_to_id and task.assigned_to_id.id != previous_assignee_ids.get(task.id):
                    task._notify_assignment()
        return result

    def _notify_assignment(self):
        """Live popup for the housekeeper a task just landed on - the one role that otherwise
        gets nothing proactive at all and would have to remember to check the task list.
        Assignment (not creation) is the meaningful event: auto-created checkout tasks start
        unassigned (see hostel.room._create_checkout_task) and only notify once someone actually
        assigns them; a task created and assigned in the same step notifies immediately too."""
        self.ensure_one()
        self.assigned_to_id._bus_send('simple_notification', {
            'type': 'info',
            'title': 'Housekeeping Task Assigned',
            'message': '%s: %s task in %s' % (
                self.room_id.display_name, self.type_id.name or 'Housekeeping', self.property_id.name),
            'sticky': True,
        })

    def action_start(self):
        for task in self:
            task.state = 'in_progress'

    def action_done(self):
        for task in self:
            task.state = 'done'
            if task.room_id.housekeeping_status == 'dirty':
                task.room_id.housekeeping_status = 'clean'

    def action_verify(self):
        for task in self:
            if task.state != 'done':
                task.state = 'done'
            task.state = 'verified'

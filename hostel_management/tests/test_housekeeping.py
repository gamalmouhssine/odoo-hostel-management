# -*- coding: utf-8 -*-
import json
from datetime import date, timedelta

from odoo.addons.bus.models.bus import channel_with_db, json_dump
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHousekeeping(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.property = cls.env['hostel.property'].create({
            'name': 'Test Property', 'code': 'TPROP4',
        })
        cls.room_type = cls.env['hostel.room.type'].create({
            'name': 'Test Type', 'code': 'TTYPE4',
            'property_id': cls.property.id, 'capacity': 1, 'default_rate': 10.0,
        })
        cls.room = cls.env['hostel.room'].create({
            'name': 'TH1', 'room_type_id': cls.room_type.id,
        })
        cls.guest = cls.env['res.partner'].create({'name': 'Housekeeping Guest', 'is_hostel_guest': True})
        cls.today = date.today()

    def _make_checked_out_booking(self, days_ago=1, nights=1):
        booking = self.env['hostel.booking'].create({
            'guest_id': self.guest.id,
            'booking_unit': 'room',
            'room_id': self.room.id,
            'check_in_date': self.today - timedelta(days=days_ago),
            'check_out_date': self.today - timedelta(days=days_ago - nights),
        })
        booking.action_confirm()
        booking.action_check_in()
        booking.action_check_out()
        return booking

    def test_checkout_creates_exactly_one_checkout_clean_task(self):
        self._make_checked_out_booking()
        tasks = self.env['hostel.housekeeping.task'].search([('room_id', '=', self.room.id)])
        self.assertEqual(len(tasks), 1)
        self.assertTrue(tasks.type_id.is_checkout_clean)
        self.assertEqual(tasks.state, 'pending')
        self.assertEqual(self.room.housekeeping_status, 'dirty')

    def test_mark_clean_completes_task_and_clears_status(self):
        self._make_checked_out_booking()
        self.room.action_mark_clean()
        self.assertEqual(self.room.housekeeping_status, 'clean')
        task = self.env['hostel.housekeeping.task'].search([('room_id', '=', self.room.id)])
        self.assertEqual(task.state, 'done')

    def test_second_checkout_before_task_done_does_not_duplicate(self):
        self._make_checked_out_booking(days_ago=5, nights=1)
        # Simulate a second guest cycling through the same room before housekeeping caught up:
        # rebook, check in, check out again while the first task is still pending.
        second_booking = self.env['hostel.booking'].create({
            'guest_id': self.guest.id,
            'booking_unit': 'room',
            'room_id': self.room.id,
            'check_in_date': self.today - timedelta(days=2),
            'check_out_date': self.today - timedelta(days=1),
        })
        second_booking.action_confirm()
        second_booking.action_check_in()
        second_booking.action_check_out()
        tasks = self.env['hostel.housekeeping.task'].search([('room_id', '=', self.room.id)])
        self.assertEqual(len(tasks), 1)

    def test_task_lifecycle_actions(self):
        self._make_checked_out_booking()
        task = self.env['hostel.housekeeping.task'].search([('room_id', '=', self.room.id)])
        task.action_start()
        self.assertEqual(task.state, 'in_progress')
        task.action_done()
        self.assertEqual(task.state, 'done')
        task.action_verify()
        self.assertEqual(task.state, 'verified')

    def _housekeeper_channel(self, user):
        return json_dump(channel_with_db(self.env.cr.dbname, user.partner_id))

    def test_creating_task_with_assignee_pops_notification(self):
        housekeeper = self.env['res.users'].create({
            'name': 'Housekeeper One', 'login': 'housekeeper_one@example.com',
        })
        task_type = self.env['hostel.housekeeping.task.type'].create({'name': 'Test Task Type'})
        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.housekeeping.task'].create({
            'room_id': self.room.id, 'type_id': task_type.id, 'assigned_to_id': housekeeper.id,
        })
        queued = self.env.cr.precommit.data.get('bus.bus.values', [])
        matches = [n for n in queued if n['channel'] == self._housekeeper_channel(housekeeper)]
        self.assertEqual(len(matches), 1)
        payload = json.loads(matches[0]['message'])['payload']
        self.assertEqual(payload['type'], 'info')
        self.assertIn(self.room.display_name, payload['message'])

    def test_creating_unassigned_task_does_not_notify(self):
        task_type = self.env['hostel.housekeeping.task.type'].create({'name': 'Test Task Type'})
        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.housekeeping.task'].create({'room_id': self.room.id, 'type_id': task_type.id})
        self.assertFalse(self.env.cr.precommit.data.get('bus.bus.values'))

    def test_reassigning_task_notifies_new_assignee_only(self):
        housekeeper_a = self.env['res.users'].create({
            'name': 'Housekeeper A', 'login': 'housekeeper_a@example.com',
        })
        housekeeper_b = self.env['res.users'].create({
            'name': 'Housekeeper B', 'login': 'housekeeper_b@example.com',
        })
        task_type = self.env['hostel.housekeeping.task.type'].create({'name': 'Test Task Type'})
        task = self.env['hostel.housekeeping.task'].create({
            'room_id': self.room.id, 'type_id': task_type.id, 'assigned_to_id': housekeeper_a.id,
        })

        self.env.cr.precommit.data.pop('bus.bus.values', None)
        task.write({'assigned_to_id': housekeeper_b.id})
        queued = self.env.cr.precommit.data.get('bus.bus.values', [])
        self.assertTrue([n for n in queued if n['channel'] == self._housekeeper_channel(housekeeper_b)])
        self.assertFalse([n for n in queued if n['channel'] == self._housekeeper_channel(housekeeper_a)])

    def test_rewriting_same_assignee_does_not_renotify(self):
        housekeeper = self.env['res.users'].create({
            'name': 'Housekeeper One', 'login': 'housekeeper_rewrite@example.com',
        })
        task_type = self.env['hostel.housekeeping.task.type'].create({'name': 'Test Task Type'})
        task = self.env['hostel.housekeeping.task'].create({
            'room_id': self.room.id, 'type_id': task_type.id, 'assigned_to_id': housekeeper.id,
        })

        self.env.cr.precommit.data.pop('bus.bus.values', None)
        task.write({'assigned_to_id': housekeeper.id, 'notes': 'Extra towels needed'})
        self.assertFalse(self.env.cr.precommit.data.get('bus.bus.values'))

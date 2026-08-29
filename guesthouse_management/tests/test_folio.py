# -*- coding: utf-8 -*-
import json
from datetime import timedelta

from odoo.addons.bus.models.bus import channel_with_db, json_dump
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFolio(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.property = cls.env['hostel.property'].create({
            'name': 'Test Property', 'code': 'TPROP3',
        })
        cls.room_type = cls.env['hostel.room.type'].create({
            'name': 'Test Type', 'code': 'TTYPE3',
            'property_id': cls.property.id, 'capacity': 2, 'default_rate': 30.0,
        })
        cls.room = cls.env['hostel.room'].create({
            'name': 'TF1', 'room_type_id': cls.room_type.id,
        })
        cls.guest = cls.env['res.partner'].create({'name': 'Folio Guest', 'is_hostel_guest': True})
        # Match fields.Date.context_today(), not bare date.today() - see test_booking.py's
        # self.today fixture for why (the two can disagree across a timezone boundary, and the
        # overdue-invoice cron below computes "today" the same context-aware way).
        cls.today = fields.Date.context_today(cls.env['hostel.booking'])

    def _make_checked_in_booking(self, nights=3):
        booking = self.env['hostel.booking'].create({
            'guest_id': self.guest.id,
            'booking_unit': 'room',
            'room_id': self.room.id,
            'check_in_date': self.today,
            'check_out_date': self.today + timedelta(days=nights),
        })
        booking.action_confirm()
        booking.action_check_in()
        return booking

    def test_check_in_creates_folio_with_stay_line(self):
        booking = self._make_checked_in_booking(nights=3)
        self.assertEqual(len(booking.folio_ids), 1)
        folio = booking.folio_ids[0]
        self.assertEqual(folio.state, 'open')
        self.assertEqual(len(folio.line_ids), 1)
        stay_line = folio.line_ids[0]
        self.assertEqual(stay_line.qty, 3)
        self.assertEqual(stay_line.unit_price, 30.0)
        self.assertEqual(folio.amount_total, 90.0)
        self.assertEqual(booking.folio_status, 'open')

    def test_folio_status_is_none_before_check_in(self):
        # No folio exists yet at draft/confirmed - that's the expected, non-alarming case (the
        # booking list only colors 'none' as a warning once state is checked_in/checked_out).
        booking = self.env['hostel.booking'].create({
            'guest_id': self.guest.id, 'booking_unit': 'room', 'room_id': self.room.id,
            'check_in_date': self.today, 'check_out_date': self.today + timedelta(days=1),
        })
        self.assertEqual(booking.folio_status, 'none')
        booking.action_confirm()
        self.assertEqual(booking.folio_status, 'none')

    def test_folio_status_tracks_invoicing(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        self.assertEqual(booking.folio_status, 'invoiced')

    def test_check_in_is_idempotent_on_folio_creation(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        booking._create_folio()
        self.assertEqual(len(booking.folio_ids), 1)
        self.assertEqual(booking.folio_ids[0], folio)

    def test_adding_line_recomputes_amount_total(self):
        booking = self._make_checked_in_booking(nights=2)
        folio = booking.folio_ids[0]
        original_total = folio.amount_total
        self.env['hostel.folio.line'].create({
            'folio_id': folio.id,
            'description': 'Laundry',
            'qty': 1,
            'unit_price': 5.0,
        })
        self.assertEqual(folio.amount_total, original_total + 5.0)

    def test_removing_line_recomputes_amount_total(self):
        booking = self._make_checked_in_booking(nights=2)
        folio = booking.folio_ids[0]
        line = self.env['hostel.folio.line'].create({
            'folio_id': folio.id, 'description': 'Laundry', 'qty': 1, 'unit_price': 5.0,
        })
        original_total = folio.amount_total
        line.unlink()
        self.assertEqual(folio.amount_total, original_total - 5.0)

    def test_create_invoice_matches_folio_lines(self):
        booking = self._make_checked_in_booking(nights=2)
        folio = booking.folio_ids[0]
        self.env['hostel.folio.line'].create({
            'folio_id': folio.id, 'description': 'Damage: broken lamp', 'qty': 1, 'unit_price': 15.0,
        })
        folio.action_create_invoice()
        self.assertEqual(folio.state, 'invoiced')
        self.assertTrue(folio.invoice_id)
        invoice = folio.invoice_id
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.guest)
        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertEqual(sum(invoice.invoice_line_ids.mapped('price_subtotal')), folio.amount_total)
        self.assertEqual(invoice.hostel_folio_id, folio)
        self.assertEqual(invoice.hostel_booking_id, booking)

    def test_cannot_invoice_twice(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        with self.assertRaises(UserError):
            folio.action_create_invoice()

    def test_cannot_invoice_empty_folio(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.line_ids.unlink()
        with self.assertRaises(UserError):
            folio.action_create_invoice()

    def test_cannot_delete_invoiced_folio(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        with self.assertRaises(UserError):
            folio.unlink()

    def test_can_delete_open_folio(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.unlink()
        self.assertFalse(booking.folio_ids)
        # This is exactly the case the booking list's decoration-danger targets: still
        # checked-in, but folio_status flips back to 'none' once its only folio is gone.
        self.assertEqual(booking.folio_status, 'none')

    def test_action_create_folio_recovers_a_deleted_open_folio(self):
        booking = self._make_checked_in_booking(nights=4)
        booking.folio_ids.unlink()
        self.assertFalse(booking.folio_ids)
        booking.action_create_folio()
        self.assertEqual(len(booking.folio_ids), 1)
        self.assertEqual(booking.folio_ids.line_ids.qty, 4)

    def test_action_create_folio_is_idempotent(self):
        booking = self._make_checked_in_booking()
        existing = booking.folio_ids
        booking.action_create_folio()
        self.assertEqual(booking.folio_ids, existing)

    def test_action_create_folio_blocked_before_check_in(self):
        booking = self.env['hostel.booking'].create({
            'guest_id': self.guest.id,
            'booking_unit': 'room',
            'room_id': self.room.id,
            'check_in_date': self.today,
            'check_out_date': self.today + timedelta(days=1),
        })
        with self.assertRaises(UserError):
            booking.action_create_folio()

    def test_cancelling_invoice_reverts_folio_to_open(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        first_invoice = folio.invoice_id
        first_invoice.button_cancel()
        self.assertEqual(folio.state, 'open')
        self.assertFalse(folio.invoice_id)
        # The folio's own lines survive a cancelled invoice, so it can be billed again.
        self.assertTrue(folio.line_ids)
        folio.action_create_invoice()
        self.assertEqual(folio.state, 'invoiced')
        self.assertNotEqual(folio.invoice_id, first_invoice)

    def test_deleting_invoice_reverts_folio_to_open(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        folio.invoice_id.unlink()
        self.assertEqual(folio.state, 'open')
        self.assertFalse(folio.invoice_id)

    def test_fully_paying_invoice_reflects_on_folio_payment_state(self):
        # folio.state itself stays 'invoiced' - deliberately not duplicated into a second
        # 'paid' state (see hostel_folio.py's help text on the field for why: nothing on this
        # model's side can reliably hook account.move's payment_state recomputation, which
        # updates via the ORM's internal recompute path, not a plain write()). payment_state
        # is a live related field instead, and this confirms it actually tracks a real payment.
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        invoice = folio.invoice_id
        invoice.action_post()
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({})
        payment_register._create_payments()
        self.assertEqual(folio.state, 'invoiced')
        self.assertEqual(folio.payment_state, 'paid')

    def _manager_channel(self, manager):
        return json_dump(channel_with_db(self.env.cr.dbname, manager.partner_id))

    def _silence_other_pending_overdue_invoices(self):
        # Same shared-dev-database hermeticity concern as test_booking.py's reminder-cron
        # tests: a freshly-created, unrestricted manager would also get notified about any
        # OTHER real overdue folio already sitting in this database (e.g. demo data), which
        # would break an exact-count assertion below.
        self.env['hostel.folio'].search([
            ('state', '=', 'invoiced'),
            ('invoice_id.payment_state', 'not in', ('paid', 'in_payment', 'reversed')),
            ('invoice_id.invoice_date_due', '<', self.today),
        ]).write({'payment_reminder_notified': True})

    def test_cron_overdue_invoice_reminder_notifies_and_flags_once(self):
        self._silence_other_pending_overdue_invoices()
        manager_group = self.env.ref('guesthouse_management.group_hostel_manager')
        manager = self.env['res.users'].create({
            'name': 'Overdue Invoice Manager', 'login': 'overdue_invoice_manager@example.com',
            'group_ids': [(6, 0, [manager_group.id])],
        })
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        invoice = folio.invoice_id
        invoice.action_post()
        invoice.invoice_date_due = self.today - timedelta(days=1)
        self.assertFalse(folio.payment_reminder_notified)

        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.folio']._cron_overdue_invoice_reminders()
        queued = self.env.cr.precommit.data.get('bus.bus.values', [])
        matches = [n for n in queued if n['channel'] == self._manager_channel(manager)]
        self.assertEqual(len(matches), 1)
        payload = json.loads(matches[0]['message'])['payload']
        self.assertEqual(payload['type'], 'danger')
        self.assertIn(booking.name, payload['message'])
        self.assertTrue(folio.payment_reminder_notified)

        # Re-running the cron must not notify the same overdue invoice a second time.
        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.folio']._cron_overdue_invoice_reminders()
        self.assertFalse(self.env.cr.precommit.data.get('bus.bus.values'))

    def test_cron_overdue_invoice_reminder_ignores_invoice_not_yet_due(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        folio.invoice_id.action_post()
        folio.invoice_id.invoice_date_due = self.today + timedelta(days=5)

        self.env['hostel.folio']._cron_overdue_invoice_reminders()
        self.assertFalse(folio.payment_reminder_notified)

    def test_cron_overdue_invoice_reminder_ignores_paid_invoice(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        invoice = folio.invoice_id
        invoice.action_post()
        invoice.invoice_date_due = self.today - timedelta(days=1)
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({})
        payment_register._create_payments()

        self.env['hostel.folio']._cron_overdue_invoice_reminders()
        self.assertFalse(folio.payment_reminder_notified)

    def test_reinvoicing_resets_payment_reminder_flag(self):
        booking = self._make_checked_in_booking()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        folio.invoice_id.action_post()
        folio.invoice_id.invoice_date_due = self.today - timedelta(days=1)
        self.env['hostel.folio']._cron_overdue_invoice_reminders()
        self.assertTrue(folio.payment_reminder_notified)

        folio.invoice_id.button_cancel()
        folio.action_create_invoice()
        self.assertFalse(folio.payment_reminder_notified)

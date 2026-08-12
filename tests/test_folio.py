# -*- coding: utf-8 -*-
from datetime import date, timedelta

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
        cls.today = date.today()

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
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertEqual(folio.state, 'invoiced')
        self.assertEqual(folio.payment_state, 'paid')

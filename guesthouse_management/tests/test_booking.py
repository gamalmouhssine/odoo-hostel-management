# -*- coding: utf-8 -*-
import json
from datetime import date, timedelta

from odoo.addons.bus.models.bus import channel_with_db, json_dump
from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBooking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.property = cls.env['hostel.property'].create({
            'name': 'Test Property',
            'code': 'TPROP2',
        })
        cls.room_type = cls.env['hostel.room.type'].create({
            'name': 'Test Type',
            'code': 'TTYPE',
            'property_id': cls.property.id,
            'capacity': 6,
            'default_rate': 20.0,
        })
        cls.room_a = cls.env['hostel.room'].create({
            'name': 'TA', 'room_type_id': cls.room_type.id,
        })
        cls.room_b = cls.env['hostel.room'].create({
            'name': 'TB', 'room_type_id': cls.room_type.id,
        })
        cls.bed_b1 = cls.env['hostel.bed'].create({'name': 'TB-1', 'room_id': cls.room_b.id})
        cls.room_dorm = cls.env['hostel.room'].create({
            'name': 'TDORM', 'room_type_id': cls.room_type.id,
        })
        cls.bed_dorm_1 = cls.env['hostel.bed'].create({'name': 'TDORM-1', 'room_id': cls.room_dorm.id})
        cls.bed_dorm_2 = cls.env['hostel.bed'].create({'name': 'TDORM-2', 'room_id': cls.room_dorm.id})
        cls.guest = cls.env['res.partner'].create({'name': 'Test Guest', 'is_hostel_guest': True})
        cls.guest_2 = cls.env['res.partner'].create({'name': 'Test Guest 2', 'is_hostel_guest': True})
        # Match fields.Date.context_today(), not the bare stdlib date.today() - the reminder
        # crons compute "today" via the former (env-user-timezone-aware), and this suite's
        # fixture dates need to agree with that or boundary-sensitive cron tests go flaky
        # whenever the two disagree (e.g. near a UTC/local-timezone day rollover).
        cls.today = fields.Date.context_today(cls.env['hostel.booking'])

    def _make_booking(self, **values):
        base = {
            'guest_id': self.guest.id,
            'booking_unit': 'room',
            'room_id': self.room_a.id,
            'check_in_date': self.today + timedelta(days=1),
            'check_out_date': self.today + timedelta(days=5),
        }
        base.update(values)
        return self.env['hostel.booking'].create(base)

    def test_overlap_room_vs_room(self):
        self._make_booking(room_id=self.room_a.id, check_in_date=self.today + timedelta(days=1),
                            check_out_date=self.today + timedelta(days=5))
        with self.assertRaises(ValidationError):
            self._make_booking(room_id=self.room_a.id, check_in_date=self.today + timedelta(days=3),
                                check_out_date=self.today + timedelta(days=7))

    def test_overlap_bed_vs_bed(self):
        self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_b1.id,
                            check_in_date=self.today + timedelta(days=1),
                            check_out_date=self.today + timedelta(days=5))
        with self.assertRaises(ValidationError):
            self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_b1.id,
                                check_in_date=self.today + timedelta(days=3),
                                check_out_date=self.today + timedelta(days=7))

    def test_overlap_room_vs_bed_within_room(self):
        # Whole-room booking first, then a bed within that same room for overlapping dates.
        self._make_booking(booking_unit='room', room_id=self.room_b.id,
                            check_in_date=self.today + timedelta(days=1),
                            check_out_date=self.today + timedelta(days=5))
        with self.assertRaises(ValidationError):
            self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_b1.id,
                                check_in_date=self.today + timedelta(days=3),
                                check_out_date=self.today + timedelta(days=7))

    def test_overlap_bed_vs_room_within_room(self):
        # Reverse order: bed booking first, then a whole-room booking on its parent room.
        self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_b1.id,
                            check_in_date=self.today + timedelta(days=1),
                            check_out_date=self.today + timedelta(days=5))
        with self.assertRaises(ValidationError):
            self._make_booking(booking_unit='room', room_id=self.room_b.id,
                                check_in_date=self.today + timedelta(days=3),
                                check_out_date=self.today + timedelta(days=7))

    def test_price_computed_over_multiple_nights(self):
        booking = self._make_booking(check_in_date=self.today + timedelta(days=1),
                                      check_out_date=self.today + timedelta(days=6))
        self.assertEqual(booking.nights, 5)
        self.assertEqual(booking.rate, 20.0)
        self.assertEqual(booking.total_price, 100.0)

    def test_price_is_locked_after_room_type_rate_change(self):
        booking = self._make_booking()
        original_total = booking.total_price
        self.room_type.default_rate = 999.0
        self.assertEqual(booking.total_price, original_total)

    def test_confirm_with_invalid_date_range_blocked(self):
        booking = self._make_booking(check_in_date=self.today + timedelta(days=5),
                                      check_out_date=self.today + timedelta(days=5))
        with self.assertRaises(UserError):
            booking.action_confirm()

    def test_confirm_sets_bed_booked_and_cancel_releases_it(self):
        booking = self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_b1.id)
        booking.action_confirm()
        self.assertEqual(self.bed_b1.status, 'booked')
        booking.action_cancel()
        self.assertEqual(self.bed_b1.status, 'available')

    def test_no_show_releases_bed_and_does_not_block_rebooking(self):
        booking = self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_b1.id)
        booking.action_confirm()
        booking.action_no_show()
        self.assertEqual(booking.state, 'no_show')
        self.assertEqual(self.bed_b1.status, 'available')
        # A no-show must not permanently block the bed for the same dates.
        rebooking = self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_b1.id)
        rebooking.action_confirm()
        self.assertEqual(rebooking.state, 'confirmed')

    def test_check_in_room_level_occupies_all_beds(self):
        booking = self._make_booking(booking_unit='room', room_id=self.room_dorm.id)
        booking.action_confirm()
        booking.action_check_in()
        self.assertEqual(self.room_dorm.state, 'occupied')
        self.assertEqual(self.bed_dorm_1.status, 'occupied')
        self.assertEqual(self.bed_dorm_2.status, 'occupied')

    def test_check_in_bed_level_partial_occupancy_keeps_room_available(self):
        booking = self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_dorm_1.id)
        booking.action_confirm()
        booking.action_check_in()
        self.assertEqual(self.bed_dorm_1.status, 'occupied')
        self.assertEqual(self.bed_dorm_2.status, 'available')
        self.assertEqual(self.room_dorm.state, 'available')

    def test_check_in_bed_level_full_occupancy_marks_room_occupied(self):
        booking_1 = self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_dorm_1.id)
        booking_1.action_confirm()
        booking_1.action_check_in()
        booking_2 = self._make_booking(
            guest_id=self.guest_2.id, booking_unit='bed', room_id=False, bed_id=self.bed_dorm_2.id)
        booking_2.action_confirm()
        booking_2.action_check_in()
        self.assertEqual(self.room_dorm.state, 'occupied')

    def test_check_out_room_level_marks_dirty_and_frees_beds(self):
        booking = self._make_booking(booking_unit='room', room_id=self.room_dorm.id)
        booking.action_confirm()
        booking.action_check_in()
        booking.action_check_out()
        self.assertEqual(booking.state, 'checked_out')
        self.assertEqual(self.room_dorm.state, 'available')
        self.assertEqual(self.room_dorm.housekeeping_status, 'dirty')
        self.assertEqual(self.bed_dorm_1.status, 'available')
        self.assertEqual(self.bed_dorm_2.status, 'available')

    def test_check_out_bed_level_marks_room_dirty(self):
        booking = self._make_booking(booking_unit='bed', room_id=False, bed_id=self.bed_dorm_1.id)
        booking.action_confirm()
        booking.action_check_in()
        booking.action_check_out()
        self.assertEqual(self.bed_dorm_1.status, 'available')
        self.assertEqual(self.room_dorm.housekeeping_status, 'dirty')

    def test_rate_plan_overrides_room_type_default_rate(self):
        rate_plan = self.env['hostel.rate_plan'].create({
            'name': 'Non-refundable',
            'room_type_id': self.room_type.id,
            'price_per_night': 9.0,
        })
        booking = self._make_booking(rate_plan_id=rate_plan.id)
        self.assertEqual(booking.rate, 9.0)

    def test_deposit_fields_round_trip(self):
        booking = self._make_booking(deposit_required=True, deposit_amount=25.0)
        self.assertTrue(booking.deposit_required)
        self.assertFalse(booking.deposit_paid)
        self.assertEqual(booking.deposit_amount, 25.0)

    def test_confirm_schedules_arrival_activity(self):
        booking = self._make_booking()
        booking.action_confirm()
        activities = booking.activity_ids
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities.summary, 'Guest arrival')
        self.assertEqual(activities.date_deadline, booking.check_in_date)

    def test_check_in_replaces_arrival_activity_with_checkout_activity(self):
        booking = self._make_booking(room_id=self.room_dorm.id, booking_unit='room')
        booking.action_confirm()
        booking.action_check_in()
        activities = booking.activity_ids
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities.summary, 'Guest checkout')
        self.assertEqual(activities.date_deadline, booking.check_out_date)

    def test_check_out_clears_pending_activity(self):
        booking = self._make_booking(room_id=self.room_dorm.id, booking_unit='room')
        booking.action_confirm()
        booking.action_check_in()
        booking.action_check_out()
        self.assertFalse(booking.activity_ids)

    def test_cancel_clears_pending_activity(self):
        booking = self._make_booking()
        booking.action_confirm()
        booking.action_cancel()
        self.assertFalse(booking.activity_ids)

    def test_no_show_clears_pending_activity(self):
        booking = self._make_booking()
        booking.action_confirm()
        booking.action_no_show()
        self.assertFalse(booking.activity_ids)

    def _silence_other_pending_reminders(self):
        # This suite runs against a shared dev database that may already carry other real
        # bookings relevant to the front-desk reminder crons (e.g. demo data) - neutralize them
        # so cron assertions below only see the one booking this test itself creates. Scoped to
        # the test's own transaction/savepoint, so nothing here touches real data permanently.
        self.env['hostel.booking'].search([
            ('state', '=', 'checked_in'), ('check_out_date', '=', self.today),
        ]).write({'checkout_reminder_notified': True})
        self.env['hostel.booking'].search([
            ('state', '=', 'confirmed'), ('check_in_date', '=', self.today),
        ]).write({'arrival_reminder_notified': True})
        self.env['hostel.booking'].search([
            ('state', '=', 'confirmed'), ('check_in_date', '<', self.today),
        ]).action_cancel()
        self.env['hostel.booking'].search([
            ('state', '=', 'checked_in'), ('check_out_date', '<', self.today),
        ]).write({'overstay_reminder_notified': True})

    def _manager_channel(self, manager):
        return json_dump(channel_with_db(self.env.cr.dbname, manager.partner_id))

    def test_cron_checkout_reminder_pops_notification_and_flags_once(self):
        self._silence_other_pending_reminders()
        manager_group = self.env.ref('guesthouse_management.group_hostel_manager')
        manager = self.env['res.users'].create({
            'name': 'Reminder Manager', 'login': 'reminder_manager@example.com',
            'group_ids': [(6, 0, [manager_group.id])],
        })
        booking = self._make_booking(
            check_in_date=self.today - timedelta(days=2), check_out_date=self.today)
        booking.action_confirm()
        booking.action_check_in()
        self.assertFalse(booking.checkout_reminder_notified)

        # _sendone() queues onto cr.precommit synchronously (real send only happens on an actual
        # commit, which a TransactionCase never does) - reading that queue directly is the
        # honest way to confirm a notification was really dispatched, not just that no exception
        # was raised.
        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.booking']._cron_checkout_reminders()
        queued = self.env.cr.precommit.data.get('bus.bus.values', [])
        manager_channel = json_dump(channel_with_db(self.env.cr.dbname, manager.partner_id))
        matches = [n for n in queued if n['channel'] == manager_channel]
        self.assertEqual(len(matches), 1)
        payload = json.loads(matches[0]['message'])['payload']
        self.assertEqual(payload['type'], 'warning')
        self.assertIn(booking.name, payload['message'])
        self.assertTrue(booking.checkout_reminder_notified)

        # Re-running the cron must not notify the same booking a second time.
        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.booking']._cron_checkout_reminders()
        self.assertFalse(self.env.cr.precommit.data.get('bus.bus.values'))

    def test_cron_checkout_reminder_respects_property_scoping(self):
        self._silence_other_pending_reminders()
        manager_group = self.env.ref('guesthouse_management.group_hostel_manager')
        other_property = self.env['hostel.property'].create({'name': 'Other Property', 'code': 'OTHERP'})
        scoped_manager = self.env['res.users'].create({
            'name': 'Other Property Manager', 'login': 'other_property_manager@example.com',
            'group_ids': [(6, 0, [manager_group.id])],
            'hostel_property_ids': [(6, 0, [other_property.id])],
        })
        booking = self._make_booking(
            check_in_date=self.today - timedelta(days=2), check_out_date=self.today)
        booking.action_confirm()
        booking.action_check_in()

        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.booking']._cron_checkout_reminders()
        queued = self.env.cr.precommit.data.get('bus.bus.values', [])
        scoped_channel = json_dump(channel_with_db(self.env.cr.dbname, scoped_manager.partner_id))
        # A manager scoped to a different property must not be notified about this one.
        self.assertFalse([n for n in queued if n['channel'] == scoped_channel])

    def test_cron_arrival_reminder_pops_notification_and_flags_once(self):
        self._silence_other_pending_reminders()
        manager_group = self.env.ref('guesthouse_management.group_hostel_manager')
        manager = self.env['res.users'].create({
            'name': 'Arrival Manager', 'login': 'arrival_manager@example.com',
            'group_ids': [(6, 0, [manager_group.id])],
        })
        booking = self._make_booking(
            check_in_date=self.today, check_out_date=self.today + timedelta(days=2))
        booking.action_confirm()
        self.assertFalse(booking.arrival_reminder_notified)

        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.booking']._cron_arrival_reminders()
        queued = self.env.cr.precommit.data.get('bus.bus.values', [])
        matches = [n for n in queued if n['channel'] == self._manager_channel(manager)]
        self.assertEqual(len(matches), 1)
        payload = json.loads(matches[0]['message'])['payload']
        self.assertEqual(payload['type'], 'info')
        self.assertIn(booking.name, payload['message'])
        self.assertTrue(booking.arrival_reminder_notified)

        # Re-running the cron must not notify the same booking a second time.
        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.booking']._cron_arrival_reminders()
        self.assertFalse(self.env.cr.precommit.data.get('bus.bus.values'))

    def test_cron_arrival_reminder_ignores_future_and_checked_in_bookings(self):
        self._silence_other_pending_reminders()
        future_booking = self._make_booking(
            check_in_date=self.today + timedelta(days=1), check_out_date=self.today + timedelta(days=3))
        future_booking.action_confirm()
        checked_in_booking = self._make_booking(
            room_id=self.room_b.id,
            check_in_date=self.today, check_out_date=self.today + timedelta(days=1))
        checked_in_booking.action_confirm()
        checked_in_booking.action_check_in()

        self.env['hostel.booking']._cron_arrival_reminders()
        self.assertFalse(future_booking.arrival_reminder_notified)
        # Already checked in - the arrival already happened, nothing to remind about.
        self.assertFalse(checked_in_booking.arrival_reminder_notified)

    def test_cron_auto_no_show_releases_unit_and_notifies(self):
        self._silence_other_pending_reminders()
        manager_group = self.env.ref('guesthouse_management.group_hostel_manager')
        manager = self.env['res.users'].create({
            'name': 'No-show Manager', 'login': 'no_show_manager@example.com',
            'group_ids': [(6, 0, [manager_group.id])],
        })
        booking = self._make_booking(
            check_in_date=self.today - timedelta(days=1), check_out_date=self.today + timedelta(days=1))
        booking.action_confirm()
        self.assertEqual(self.room_a.state, 'available')

        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.booking']._cron_auto_no_show()
        self.assertEqual(booking.state, 'no_show')
        self.assertEqual(self.room_a.state, 'available')  # released, not left dangling

        queued = self.env.cr.precommit.data.get('bus.bus.values', [])
        matches = [n for n in queued if n['channel'] == self._manager_channel(manager)]
        self.assertEqual(len(matches), 1)
        payload = json.loads(matches[0]['message'])['payload']
        self.assertEqual(payload['type'], 'danger')
        self.assertIn(booking.name, payload['message'])

    def test_cron_auto_no_show_does_not_touch_bookings_checking_in_today_or_later(self):
        self._silence_other_pending_reminders()
        today_booking = self._make_booking(
            check_in_date=self.today, check_out_date=self.today + timedelta(days=2))
        today_booking.action_confirm()

        self.env['hostel.booking']._cron_auto_no_show()
        self.assertEqual(today_booking.state, 'confirmed')

    def test_cron_overstay_reminder_pops_notification_and_flags_once(self):
        self._silence_other_pending_reminders()
        manager_group = self.env.ref('guesthouse_management.group_hostel_manager')
        manager = self.env['res.users'].create({
            'name': 'Overstay Manager', 'login': 'overstay_manager@example.com',
            'group_ids': [(6, 0, [manager_group.id])],
        })
        booking = self._make_booking(
            check_in_date=self.today - timedelta(days=3), check_out_date=self.today - timedelta(days=1))
        booking.action_confirm()
        booking.action_check_in()
        self.assertFalse(booking.overstay_reminder_notified)

        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.booking']._cron_overstay_reminders()
        queued = self.env.cr.precommit.data.get('bus.bus.values', [])
        matches = [n for n in queued if n['channel'] == self._manager_channel(manager)]
        self.assertEqual(len(matches), 1)
        payload = json.loads(matches[0]['message'])['payload']
        self.assertEqual(payload['type'], 'danger')
        self.assertIn(booking.name, payload['message'])
        self.assertTrue(booking.overstay_reminder_notified)
        # Booking is left checked_in - this cron only alerts, never auto-checks-out.
        self.assertEqual(booking.state, 'checked_in')

        # Re-running the cron must not notify the same booking a second time.
        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self.env['hostel.booking']._cron_overstay_reminders()
        self.assertFalse(self.env.cr.precommit.data.get('bus.bus.values'))

    def test_cron_overstay_reminder_ignores_checkouts_due_today_or_later(self):
        self._silence_other_pending_reminders()
        booking = self._make_booking(
            check_in_date=self.today - timedelta(days=1), check_out_date=self.today)
        booking.action_confirm()
        booking.action_check_in()

        self.env['hostel.booking']._cron_overstay_reminders()
        self.assertFalse(booking.overstay_reminder_notified)

    def test_check_in_blocked_when_deposit_required_but_not_paid(self):
        booking = self._make_booking(deposit_required=True, deposit_amount=25.0)
        booking.action_confirm()
        with self.assertRaises(UserError):
            booking.action_check_in()
        self.assertEqual(booking.state, 'confirmed')

    def test_check_in_allowed_once_deposit_marked_paid(self):
        booking = self._make_booking(deposit_required=True, deposit_amount=25.0)
        booking.action_confirm()
        booking.deposit_paid = True
        booking.action_check_in()
        self.assertEqual(booking.state, 'checked_in')

    def test_check_in_not_blocked_when_no_deposit_required(self):
        booking = self._make_booking(deposit_required=False)
        booking.action_confirm()
        booking.action_check_in()  # must not raise
        self.assertEqual(booking.state, 'checked_in')

    def test_confirm_blocked_for_blacklisted_guest(self):
        self.guest.write({'is_blacklisted': True, 'blacklist_reason': 'Damaged a mattress'})
        booking = self._make_booking()
        with self.assertRaises(UserError):
            booking.action_confirm()
        self.assertEqual(booking.state, 'draft')

    def test_draft_booking_can_still_be_created_for_blacklisted_guest(self):
        # The block is on confirming, not on drafting - staff can still discuss with a manager
        # before deciding, rather than being unable to even record the request.
        self.guest.is_blacklisted = True
        booking = self._make_booking()  # must not raise
        self.assertEqual(booking.state, 'draft')

    def test_confirm_allowed_once_guest_unblacklisted(self):
        self.guest.is_blacklisted = True
        booking = self._make_booking()
        self.guest.is_blacklisted = False
        booking.action_confirm()  # must not raise
        self.assertEqual(booking.state, 'confirmed')

    def test_confirm_sends_booking_confirmation_email_when_guest_has_email(self):
        self.guest.email = 'guest@example.com'
        booking = self._make_booking()
        booking.action_confirm()
        mails = self.env['mail.mail'].search([
            ('model', '=', 'hostel.booking'), ('res_id', '=', booking.id),
        ])
        self.assertEqual(len(mails), 1)
        self.assertIn(booking.name, mails.subject)
        self.assertIn(self.guest, mails.recipient_ids)

    def test_confirm_skips_email_when_guest_has_no_email(self):
        self.guest.email = False
        booking = self._make_booking()
        booking.action_confirm()  # must not raise
        mails = self.env['mail.mail'].search([
            ('model', '=', 'hostel.booking'), ('res_id', '=', booking.id),
        ])
        self.assertFalse(mails)

# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReports(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.property = cls.env['hostel.property'].create({
            'name': 'Test Property', 'code': 'TPROP5',
        })
        cls.room_type = cls.env['hostel.room.type'].create({
            'name': 'Test Type', 'code': 'TTYPE5',
            'property_id': cls.property.id, 'capacity': 1, 'default_rate': 20.0,
        })
        cls.room_a = cls.env['hostel.room'].create({
            'name': 'TR1', 'room_type_id': cls.room_type.id,
        })
        cls.room_b = cls.env['hostel.room'].create({
            'name': 'TR2', 'room_type_id': cls.room_type.id,
        })
        cls.guest = cls.env['res.partner'].create({'name': 'Report Guest', 'is_hostel_guest': True})
        cls.today = date.today()

    def _make_checked_in_booking(self, room=None, check_in_date=None, check_out_date=None):
        booking = self.env['hostel.booking'].create({
            'guest_id': self.guest.id,
            'booking_unit': 'room',
            'room_id': (room or self.room_a).id,
            'check_in_date': check_in_date or self.today,
            'check_out_date': check_out_date or self.today + timedelta(days=1),
        })
        booking.action_confirm()
        booking.action_check_in()
        return booking

    def test_occupancy_lines_fully_inside_window(self):
        # 3-night booking fully inside a 10-day window, on one of 2 rooms of this type.
        self._make_checked_in_booking(
            room=self.room_a,
            check_in_date=self.today + timedelta(days=2),
            check_out_date=self.today + timedelta(days=5),
        )
        wizard = self.env['hostel.occupancy.report.wizard'].create({
            'date_from': self.today,
            'date_to': self.today + timedelta(days=9),  # 10-day window
            'property_id': self.property.id,
        })
        lines = wizard._get_occupancy_lines()
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line['nights_sold'], 3)
        self.assertEqual(line['available_room_nights'], 20)  # 2 rooms x 10 days
        self.assertAlmostEqual(line['occupancy_pct'], 15.0)
        self.assertEqual(line['revenue'], 60.0)  # 3 nights x 20.0
        self.assertEqual(line['adr'], 20.0)

    def test_occupancy_lines_clip_booking_to_window(self):
        # Booking starts 2 days before the window and ends 2 days after it: only the 6 nights
        # that actually fall inside [date_from, date_to] should count.
        self._make_checked_in_booking(
            room=self.room_a,
            check_in_date=self.today - timedelta(days=2),
            check_out_date=self.today + timedelta(days=8),
        )
        wizard = self.env['hostel.occupancy.report.wizard'].create({
            'date_from': self.today,
            'date_to': self.today + timedelta(days=5),  # 6-day window
            'property_id': self.property.id,
        })
        lines = wizard._get_occupancy_lines()
        self.assertEqual(lines[0]['nights_sold'], 6)
        self.assertEqual(lines[0]['revenue'], 120.0)

    def test_occupancy_lines_empty_when_no_bookings(self):
        wizard = self.env['hostel.occupancy.report.wizard'].create({
            'date_from': self.today + timedelta(days=100),
            'date_to': self.today + timedelta(days=110),
            'property_id': self.property.id,
        })
        self.assertEqual(wizard._get_occupancy_lines(), [])

    def test_reports_render_without_error(self):
        booking = self._make_checked_in_booking(
            check_in_date=self.today, check_out_date=self.today + timedelta(days=2))
        folio = booking.folio_ids[0]
        wizard = self.env['hostel.occupancy.report.wizard'].create({
            'date_from': self.today - timedelta(days=10),
            'date_to': self.today + timedelta(days=10),
        })
        report_model = self.env['ir.actions.report']
        for report_ref, res_ids in [
            ('guesthouse_management.action_report_hostel_booking_confirmation', [booking.id]),
            ('guesthouse_management.action_report_hostel_checkin_registration', [booking.id]),
            ('guesthouse_management.action_report_hostel_folio', [folio.id]),
            ('guesthouse_management.action_report_hostel_arrivals_departures', [self.property.id]),
            ('guesthouse_management.action_report_hostel_occupancy', [wizard.id]),
        ]:
            html, _report_type = report_model._render_qweb_html(report_ref, res_ids)
            self.assertTrue(html, "%s rendered empty output" % report_ref)

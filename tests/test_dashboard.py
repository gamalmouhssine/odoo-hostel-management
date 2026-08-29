# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.property_a = cls.env['hostel.property'].create({'name': 'Dash Property A', 'code': 'DASHA'})
        cls.property_b = cls.env['hostel.property'].create({'name': 'Dash Property B', 'code': 'DASHB'})
        cls.room_type_a = cls.env['hostel.room.type'].create({
            'name': 'Dash Type A', 'code': 'DTYPEA', 'property_id': cls.property_a.id,
            'capacity': 1, 'default_rate': 40.0,
        })
        cls.room_type_b = cls.env['hostel.room.type'].create({
            'name': 'Dash Type B', 'code': 'DTYPEB', 'property_id': cls.property_b.id,
            'capacity': 1, 'default_rate': 40.0,
        })
        # Property A: 2 rooms, Property B: 1 room - every room carries its own bed record, even
        # single-occupancy ones (see phase1_master_data.xml's own comment on this), since
        # occupancy is tracked bed-by-bed (hostel.property._compute_today_occupancy_rate does
        # the same) - a room with no bed record would never register as occupied.
        cls.room_a1 = cls.env['hostel.room'].create({'name': 'DA1', 'room_type_id': cls.room_type_a.id})
        cls.bed_a1 = cls.env['hostel.bed'].create({'name': 'DA1-A', 'room_id': cls.room_a1.id})
        cls.room_a2 = cls.env['hostel.room'].create({'name': 'DA2', 'room_type_id': cls.room_type_a.id})
        cls.bed_a2 = cls.env['hostel.bed'].create({'name': 'DA2-A', 'room_id': cls.room_a2.id})
        cls.room_b1 = cls.env['hostel.room'].create({'name': 'DB1', 'room_type_id': cls.room_type_b.id})
        cls.bed_b1 = cls.env['hostel.bed'].create({'name': 'DB1-A', 'room_id': cls.room_b1.id})
        cls.guest = cls.env['res.partner'].create({'name': 'Dashboard Guest', 'is_hostel_guest': True})
        # Match fields.Date.context_today(), not bare date.today() - see test_booking.py's
        # self.today fixture for why (the two can disagree across a timezone boundary).
        cls.today = fields.Date.context_today(cls.env['hostel.booking'])

    def _make_booking(self, room, **values):
        base = {
            'guest_id': self.guest.id, 'booking_unit': 'room', 'room_id': room.id,
            'check_in_date': self.today - timedelta(days=1),
            'check_out_date': self.today + timedelta(days=1),
        }
        base.update(values)
        return self.env['hostel.booking'].create(base)

    def test_percentage_fields_store_a_ratio_not_a_percentage(self):
        # The exact bug the client caught live in the UI: occupancy_ratio_today must be a 0-1
        # ratio (e.g. 0.5 for 50%), because Odoo's `percentage` widget multiplies by 100 itself
        # for display (confirmed against formatPercentage() in web's formatters.js) - storing an
        # already-multiplied value like 50.0 renders as "5000%".
        booking = self._make_booking(self.room_a1)
        booking.action_confirm()
        booking.action_check_in()
        dashboard = self.env['hostel.dashboard'].create({'property_id': self.property_a.id})
        self.assertEqual(dashboard.occupancy_ratio_today, 0.5)
        self.assertLessEqual(dashboard.occupancy_ratio_today, 1.0)

    def test_dashboard_kpis_aggregate_across_all_properties_by_default(self):
        # This suite runs against a shared dev database that may already carry other real
        # checked-in bookings (demo data) - assert the increase this booking causes, not an
        # absolute count, same hermeticity concern as test_booking.py's reminder-cron tests.
        baseline_in_house = self.env['hostel.booking'].search_count([('state', '=', 'checked_in')])

        booking = self._make_booking(self.room_a1)
        booking.action_confirm()
        booking.action_check_in()

        dashboard = self.env['hostel.dashboard'].create({})
        self.assertEqual(dashboard.in_house_count, baseline_in_house + 1)

    def test_dashboard_scopes_to_selected_property(self):
        booking_a = self._make_booking(self.room_a1)
        booking_a.action_confirm()
        booking_a.action_check_in()

        dashboard = self.env['hostel.dashboard'].create({'property_id': self.property_b.id})
        # Property B has no bookings of its own - scoping must exclude property A's.
        self.assertEqual(dashboard.in_house_count, 0)
        self.assertEqual(dashboard.occupancy_ratio_today, 0.0)

        dashboard_a = self.env['hostel.dashboard'].create({'property_id': self.property_a.id})
        self.assertEqual(dashboard_a.in_house_count, 1)
        self.assertEqual(dashboard_a.occupancy_ratio_today, 0.5)  # 1 of 2 rooms in property A

    def test_dashboard_occupancy_status_thresholds(self):
        # Scoped to property A alone (2 rooms/beds) throughout - avoids the shared-dev-database
        # pollution issue above, and property B doesn't need to be involved to exercise all
        # three thresholds.
        dashboard = self.env['hostel.dashboard'].create({'property_id': self.property_a.id})
        self.assertEqual(dashboard.occupancy_ratio_today, 0.0)
        self.assertEqual(dashboard.occupancy_status, 'warning')

        booking_a1 = self._make_booking(self.room_a1)
        booking_a1.action_confirm()
        booking_a1.action_check_in()
        # 1 of 2 rooms occupied -> 50% -> between 30 and 70 -> steady.
        dashboard = self.env['hostel.dashboard'].create({'property_id': self.property_a.id})
        self.assertEqual(dashboard.occupancy_status, 'primary')

        booking_a2 = self._make_booking(self.room_a2)
        booking_a2.action_confirm()
        booking_a2.action_check_in()
        # 2 of 2 -> 100% -> strong.
        dashboard = self.env['hostel.dashboard'].create({'property_id': self.property_a.id})
        self.assertEqual(dashboard.occupancy_status, 'success')

    def test_dashboard_arrivals_and_departures_today(self):
        arriving = self._make_booking(
            self.room_a1, check_in_date=self.today, check_out_date=self.today + timedelta(days=2))
        arriving.action_confirm()

        checked_in = self._make_booking(
            self.room_a2, check_in_date=self.today - timedelta(days=1), check_out_date=self.today)
        checked_in.action_confirm()
        checked_in.action_check_in()

        dashboard = self.env['hostel.dashboard'].create({})
        self.assertEqual(dashboard.arrivals_today_count, 1)
        self.assertEqual(dashboard.departures_today_count, 1)

    def test_dashboard_period_kpis_and_breakdown_scoped_to_property(self):
        # 2-night stay in property A, entirely inside the default date range (this month).
        booking = self._make_booking(
            self.room_a1, check_in_date=self.today, check_out_date=self.today + timedelta(days=2))
        booking.action_confirm()
        booking.action_check_in()

        dashboard = self.env['hostel.dashboard'].create({
            'property_id': self.property_a.id,
            'date_from': self.today, 'date_to': self.today + timedelta(days=5),
        })
        self.assertEqual(dashboard.nights_sold_period, 2)
        self.assertEqual(dashboard.revenue_period, 2 * 40.0)
        self.assertEqual(dashboard.adr_period, 40.0)
        self.assertEqual(len(dashboard.line_ids), 1)
        line = dashboard.line_ids[0]
        self.assertEqual(line.room_type_id, self.room_type_a)
        self.assertEqual(line.nights_sold, 2)
        self.assertEqual(line.available_room_nights, 2 * 6)  # 2 rooms x 6 days in range
        self.assertAlmostEqual(line.occupancy_ratio, 2.0 / 12, places=4)
        self.assertLessEqual(line.occupancy_ratio, 1.0)

    def test_dashboard_period_excludes_bookings_outside_the_range(self):
        booking = self._make_booking(
            self.room_a1, check_in_date=self.today - timedelta(days=30),
            check_out_date=self.today - timedelta(days=28))
        booking.action_confirm()
        booking.action_check_in()
        booking.action_check_out()

        dashboard = self.env['hostel.dashboard'].create({
            'property_id': self.property_a.id,
            'date_from': self.today, 'date_to': self.today + timedelta(days=5),
        })
        self.assertEqual(dashboard.nights_sold_period, 0)
        self.assertEqual(dashboard.revenue_period, 0.0)
        self.assertFalse(dashboard.line_ids)

    def test_get_view_renders_for_staff(self):
        staff_group = self.env.ref('hostel_management.group_hostel_staff')
        staff_user = self.env['res.users'].create({
            'name': 'Dashboard Staff', 'login': 'dashboard_staff@example.com',
            'group_ids': [(6, 0, [staff_group.id])],
        })
        view = self.env['hostel.dashboard'].with_user(staff_user).get_view(view_type='form')
        self.assertIn('o_hst_kpi_grid', view['arch'])

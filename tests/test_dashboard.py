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
        # Property A: 2 rooms, one occupied -> 50% occupancy. Property B: 1 room, unoccupied.
        # Every room, even a single-occupancy private one, carries its own bed record - see
        # phase1_master_data.xml's own comment on this. Occupancy is tracked bed-by-bed
        # (hostel.property._compute_today_occupancy_rate does the same), so a room with no bed
        # record would never register as occupied no matter what bookings it has.
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
        self.assertEqual(dashboard.occupancy_pct_today, 0.0)

        dashboard_a = self.env['hostel.dashboard'].create({'property_id': self.property_a.id})
        self.assertEqual(dashboard_a.in_house_count, 1)
        self.assertEqual(dashboard_a.occupancy_pct_today, 50.0)  # 1 of 2 rooms in property A

    def test_dashboard_occupancy_status_thresholds(self):
        # Scoped to property A alone (2 rooms/beds) throughout - avoids the same shared-dev-
        # database pollution as the aggregate test above, and property B doesn't need to be
        # involved at all to exercise all three thresholds.
        dashboard = self.env['hostel.dashboard'].create({'property_id': self.property_a.id})
        self.assertEqual(dashboard.occupancy_pct_today, 0.0)
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

    def test_dashboard_revenue_mtd_sums_posted_invoices_this_month(self):
        booking = self._make_booking(self.room_a1)
        booking.action_confirm()
        booking.action_check_in()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()
        folio.invoice_id.action_post()

        dashboard = self.env['hostel.dashboard'].create({})
        self.assertAlmostEqual(dashboard.revenue_mtd, folio.amount_total, places=2)

    def test_dashboard_revenue_mtd_excludes_unposted_invoices(self):
        booking = self._make_booking(self.room_a1)
        booking.action_confirm()
        booking.action_check_in()
        folio = booking.folio_ids[0]
        folio.action_create_invoice()  # left in draft, never posted

        dashboard = self.env['hostel.dashboard'].create({})
        self.assertEqual(dashboard.revenue_mtd, 0.0)

    def test_get_view_renders_for_staff(self):
        staff_group = self.env.ref('hostel_management.group_hostel_staff')
        staff_user = self.env['res.users'].create({
            'name': 'Dashboard Staff', 'login': 'dashboard_staff@example.com',
            'group_ids': [(6, 0, [staff_group.id])],
        })
        view = self.env['hostel.dashboard'].with_user(staff_user).get_view(view_type='form')
        self.assertIn('o_hst_kpi_grid', view['arch'])

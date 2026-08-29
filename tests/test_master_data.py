# -*- coding: utf-8 -*-
from datetime import date, timedelta

from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestMasterData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.property = cls.env['hostel.property'].create({
            'name': 'Test Property',
            'code': 'TPROP',
        })
        cls.room_type = cls.env['hostel.room.type'].create({
            'name': 'Test Dorm',
            'code': 'TDORM',
            'property_id': cls.property.id,
            'capacity': 6,
            'default_rate': 10.0,
        })

    def test_room_capacity_defaults_from_room_type(self):
        room = self.env['hostel.room'].create({
            'name': 'T101',
            'room_type_id': self.room_type.id,
        })
        self.assertEqual(room.capacity, 6)

    def test_room_capacity_override_persists(self):
        room = self.env['hostel.room'].create({
            'name': 'T102',
            'room_type_id': self.room_type.id,
            'capacity': 4,
        })
        self.assertEqual(room.capacity, 4)
        # Editing an unrelated field must not reset the manual override.
        room.write({'floor': '1'})
        self.assertEqual(room.capacity, 4)

    @mute_logger('odoo.sql_db')
    def test_room_type_code_uniqueness_rejected(self):
        with self.assertRaises(IntegrityError):
            self.env['hostel.room.type'].create({
                'name': 'Duplicate Dorm',
                'code': 'TDORM',
                'property_id': self.property.id,
            })

    def test_room_state_and_housekeeping_status_are_independent(self):
        # A room can be occupied and still need cleaning at the same time - the old single
        # `status` field could not represent that combination.
        room = self.env['hostel.room'].create({
            'name': 'T103',
            'room_type_id': self.room_type.id,
            'state': 'occupied',
            'housekeeping_status': 'dirty',
        })
        self.assertEqual(room.state, 'occupied')
        self.assertEqual(room.housekeeping_status, 'dirty')
        room.housekeeping_status = 'clean'
        self.assertEqual(room.state, 'occupied')

    def test_bed_status_has_no_dirty_value(self):
        # Housekeeping now lives on hostel.room only; hostel.bed keeps a pure occupancy status.
        room = self.env['hostel.room'].create({
            'name': 'T104', 'room_type_id': self.room_type.id,
        })
        bed = self.env['hostel.bed'].create({'name': 'T104-A', 'room_id': room.id})
        self.assertIn(bed.status, ('available', 'booked', 'occupied', 'maintenance'))

    def test_rate_plan_belongs_to_room_type_and_has_a_default_policy(self):
        rate_plan = self.env['hostel.rate_plan'].create({
            'name': 'Non-refundable',
            'room_type_id': self.room_type.id,
            'price_per_night': 9.0,
            'cancellation_policy_id': self.env.ref(
                'hostel_management.hostel_cancellation_policy_non_refundable').id,
        })
        self.assertEqual(rate_plan.room_type_id, self.room_type)
        self.assertEqual(rate_plan.currency_id, self.room_type.currency_id)

    def test_property_room_and_bed_counts(self):
        room = self.env['hostel.room'].create({
            'name': 'T105', 'room_type_id': self.room_type.id,
        })
        self.env['hostel.bed'].create({'name': 'T105-A', 'room_id': room.id})
        self.env['hostel.bed'].create({'name': 'T105-B', 'room_id': room.id})
        self.assertIn(room, self.property.room_ids)
        self.assertGreaterEqual(self.property.bed_count, 2)

    def test_property_occupancy_is_a_ratio_not_a_percentage(self):
        # Regression: this field is rendered with widget="percentage" in both the property form
        # and list, and that widget multiplies by 100 itself - storing an already-multiplied
        # value here displayed a literal "2608.7%" on the property form. A ratio never exceeds 1.
        prop = self.env['hostel.property'].create({'name': 'Occupancy Prop', 'code': 'OCCP'})
        room_type = self.env['hostel.room.type'].create({
            'name': 'Occupancy Type', 'code': 'OCCT', 'property_id': prop.id, 'capacity': 2,
        })
        room = self.env['hostel.room'].create({'name': 'OC1', 'room_type_id': room_type.id})
        bed_a = self.env['hostel.bed'].create({'name': 'OC1-A', 'room_id': room.id})
        self.env['hostel.bed'].create({'name': 'OC1-B', 'room_id': room.id})

        self.assertEqual(prop.today_occupancy_rate, 0.0)
        bed_a.status = 'occupied'
        prop.invalidate_recordset(['today_occupancy_rate'])
        self.assertEqual(prop.today_occupancy_rate, 0.5)  # 1 of 2 beds, NOT 50.0
        self.assertLessEqual(prop.today_occupancy_rate, 1.0)

    @mute_logger('odoo.sql_db')
    def test_amenity_name_uniqueness_rejected(self):
        self.env['hostel.amenity'].create({'name': 'Sauna'})
        with self.assertRaises(IntegrityError):
            self.env['hostel.amenity'].create({'name': 'Sauna'})

    def test_cannot_delete_room_with_booking_history(self):
        room = self.env['hostel.room'].create({'name': 'T106', 'room_type_id': self.room_type.id})
        guest = self.env['res.partner'].create({'name': 'History Guest', 'is_hostel_guest': True})
        today = date.today()
        self.env['hostel.booking'].create({
            'guest_id': guest.id, 'booking_unit': 'room', 'room_id': room.id,
            'check_in_date': today, 'check_out_date': today + timedelta(days=1),
        })
        with self.assertRaises(UserError):
            room.unlink()

    def test_can_delete_room_with_no_booking_history(self):
        room = self.env['hostel.room'].create({'name': 'T107', 'room_type_id': self.room_type.id})
        room.unlink()  # must not raise

    def test_cannot_delete_bed_with_booking_history(self):
        room = self.env['hostel.room'].create({'name': 'T108', 'room_type_id': self.room_type.id})
        bed = self.env['hostel.bed'].create({'name': 'T108-A', 'room_id': room.id})
        guest = self.env['res.partner'].create({'name': 'History Guest 2', 'is_hostel_guest': True})
        today = date.today()
        self.env['hostel.booking'].create({
            'guest_id': guest.id, 'booking_unit': 'bed', 'bed_id': bed.id,
            'check_in_date': today, 'check_out_date': today + timedelta(days=1),
        })
        with self.assertRaises(UserError):
            bed.unlink()
        # The room-level cascade (hostel.bed.room_id has ondelete='cascade') must also be
        # blocked by the same guard, not silently bypass it.
        with self.assertRaises(UserError):
            room.unlink()

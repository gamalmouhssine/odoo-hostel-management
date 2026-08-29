# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.property_a = cls.env['hostel.property'].create({'name': 'Property A', 'code': 'PROPA'})
        cls.property_b = cls.env['hostel.property'].create({'name': 'Property B', 'code': 'PROPB'})
        cls.room_type_a = cls.env['hostel.room.type'].create({
            'name': 'Type A', 'code': 'TYPEA', 'property_id': cls.property_a.id, 'capacity': 1,
        })
        cls.room_type_b = cls.env['hostel.room.type'].create({
            'name': 'Type B', 'code': 'TYPEB', 'property_id': cls.property_b.id, 'capacity': 1,
        })
        cls.room_a = cls.env['hostel.room'].create({'name': 'RA1', 'room_type_id': cls.room_type_a.id})
        cls.room_b = cls.env['hostel.room'].create({'name': 'RB1', 'room_type_id': cls.room_type_b.id})

        staff_group = cls.env.ref('guesthouse_management.group_hostel_staff')
        manager_group = cls.env.ref('guesthouse_management.group_hostel_manager')
        cls.staff_user_a = cls.env['res.users'].create({
            'name': 'Property A Staff', 'login': 'property_a_staff@example.com',
            'group_ids': [(6, 0, [staff_group.id])],
            'hostel_property_ids': [(6, 0, [cls.property_a.id])],
        })
        cls.manager_user = cls.env['res.users'].create({
            'name': 'Hostel Manager', 'login': 'hostel_manager@example.com',
            'group_ids': [(6, 0, [manager_group.id])],
        })
        cls.unscoped_staff_user = cls.env['res.users'].create({
            'name': 'Unscoped Staff', 'login': 'unscoped_staff@example.com',
            'group_ids': [(6, 0, [staff_group.id])],
        })

    def test_staff_sees_only_assigned_property_rooms(self):
        rooms = self.env['hostel.room'].with_user(self.staff_user_a).search([])
        self.assertIn(self.room_a, rooms)
        self.assertNotIn(self.room_b, rooms)

    def test_staff_cannot_read_other_property_room_directly(self):
        with self.assertRaises(AccessError):
            self.room_b.with_user(self.staff_user_a).read(['name'])

    def test_manager_sees_all_properties_unrestricted(self):
        rooms = self.env['hostel.room'].with_user(self.manager_user).search([])
        self.assertIn(self.room_a, rooms)
        self.assertIn(self.room_b, rooms)

    def test_staff_with_no_properties_assigned_sees_everything(self):
        # The critical fallback: a fresh install (or a single-property hostel that never bothers
        # assigning properties) must not silently lock staff out of their own data.
        rooms = self.env['hostel.room'].with_user(self.unscoped_staff_user).search([])
        self.assertIn(self.room_a, rooms)
        self.assertIn(self.room_b, rooms)

    def test_housekeeping_group_cannot_read_bookings(self):
        housekeeping_group = self.env.ref('guesthouse_management.group_hostel_housekeeping')
        housekeeping_user = self.env['res.users'].create({
            'name': 'Housekeeper', 'login': 'housekeeper@example.com',
            'group_ids': [(6, 0, [housekeeping_group.id])],
        })
        with self.assertRaises(AccessError):
            self.env['hostel.booking'].with_user(housekeeping_user).search([])

    def test_general_user_cannot_see_guest_id_document_fields(self):
        # Field-level groups= restriction in res_partner_views.xml - a plain internal user (not
        # hostel staff/manager) must not see id_document_* / date_of_birth on a guest's form.
        general_user = self.env['res.users'].create({
            'name': 'General User', 'login': 'general_user@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        view_infos = self.env['res.partner'].with_user(general_user).get_view(view_type='form')
        self.assertNotIn('id_document_number', view_infos['arch'])
        self.assertNotIn('date_of_birth', view_infos['arch'])

        staff_view_infos = self.env['res.partner'].with_user(self.staff_user_a).get_view(view_type='form')
        self.assertIn('id_document_number', staff_view_infos['arch'])

    def test_plain_admin_can_open_any_users_access_rights_tab(self):
        # Real bug: hostel_property_ids sits on res.users' Access Rights tab with no groups=
        # restriction, so opening it reads hostel.property - which a fresh installer's admin
        # account (not yet a member of any Hostel group) previously couldn't read at all,
        # throwing an Access Error just from opening Settings > Users. Every internal user
        # needs at least read access to hostel.property for this tab to be safely openable,
        # independent of whether they've been added to a Hostel role.
        general_user = self.env['res.users'].create({
            'name': 'General Admin', 'login': 'general_admin@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.staff_user_a.hostel_property_ids  # ensure a real value exists to read, not just []
        self.env['res.users'].with_user(general_user).browse(self.staff_user_a.id).read(['hostel_property_ids'])

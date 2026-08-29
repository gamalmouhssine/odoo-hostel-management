# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HostelBooking(models.Model):
    _name = 'hostel.booking'
    _description = 'Hostel Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'check_in_date desc, id desc'

    name = fields.Char(default='New', copy=False, readonly=True, index=True)
    guest_id = fields.Many2one(
        'res.partner', string='Guest', required=True, tracking=True,
        domain=[('is_hostel_guest', '=', True)])
    booking_unit = fields.Selection([
        ('room', 'Whole Room'),
        ('bed', 'Single Bed'),
    ], default='room', required=True, tracking=True)
    room_id = fields.Many2one('hostel.room', string='Room', tracking=True)
    bed_id = fields.Many2one('hostel.bed', string='Bed', tracking=True)
    room_type_id = fields.Many2one(
        'hostel.room.type', string='Room Type', compute='_compute_room_type_id', store=True,
        help='Resolved from the booked room (or the booked bed\'s room) — lets bookings be '
             'grouped/reported by room type regardless of booking_unit.')
    property_id = fields.Many2one(
        'hostel.property', related='room_type_id.property_id', store=True, string='Property')
    rate_plan_id = fields.Many2one(
        'hostel.rate_plan', string='Rate Plan', domain="[('room_type_id', '=', room_type_id)]",
        help="Optional. When set, the nightly rate is snapshotted from this plan instead of the "
             "room type's flat Default Nightly Rate.")
    check_in_date = fields.Date(required=True, tracking=True)
    check_out_date = fields.Date(required=True, tracking=True)
    nights = fields.Integer(compute='_compute_nights', store=True)
    rate = fields.Monetary(
        string='Nightly Rate',
        help='Snapshot of the rate plan (or room type\'s default rate), taken when the booking '
             'is created (and while you edit it). It is NOT affected by later changes to the '
             'rate plan/room type — and you can override it.')
    total_price = fields.Monetary(compute='_compute_total_price', store=True)
    additional_guest_ids = fields.Many2many(
        'res.partner', string='Additional Guests', domain=[('is_hostel_guest', '=', True)],
        help="Other guests sharing this stay (private-room bookings with 2+ people).")
    num_guests = fields.Integer(default=1)
    source_id = fields.Many2one('hostel.booking.source', string='Source')
    external_ref = fields.Char(string='External Reference', help="OTA confirmation number, if applicable.")
    deposit_required = fields.Boolean()
    deposit_paid = fields.Boolean()
    deposit_amount = fields.Monetary()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('checked_in', 'Checked In'),
        ('checked_out', 'Checked Out'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No-show'),
    ], default='draft', required=True, tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    folio_ids = fields.One2many('hostel.folio', 'booking_id', string='Folios')
    folio_count = fields.Integer(compute='_compute_folio_count')
    folio_status = fields.Selection([
        ('none', 'No Folio'),
        ('open', 'Open'),
        ('invoiced', 'Invoiced'),
    ], compute='_compute_folio_status', store=True,
        help="Mirrors the (usually single) folio's own state so it's visible in the booking "
             "list without opening each record. 'No Folio' is expected/normal before check-in - "
             "the interesting case is a checked-in/checked-out booking showing it, which means "
             "its folio was deleted (see action_create_folio's recovery path); the list view "
             "colors only that combination as a warning, not every not-yet-checked-in booking.")
    checkout_reminder_notified = fields.Boolean(
        default=False, copy=False,
        help="Set once _cron_checkout_reminders has already popped a same-day-checkout "
             "notification for this booking, so it fires once per stay, not on every cron run.")
    arrival_reminder_notified = fields.Boolean(
        default=False, copy=False,
        help="Set once _cron_arrival_reminders has already popped a same-day-arrival "
             "notification for this booking, so it fires once per stay, not on every cron run.")
    overstay_reminder_notified = fields.Boolean(
        default=False, copy=False,
        help="Set once _cron_overstay_reminders has already popped an overstay notification "
             "for this booking, so it fires once per stay, not on every cron run.")

    @api.depends('folio_ids')
    def _compute_folio_count(self):
        for booking in self:
            booking.folio_count = len(booking.folio_ids)

    @api.depends('folio_ids.state')
    def _compute_folio_status(self):
        for booking in self:
            if not booking.folio_ids:
                booking.folio_status = 'none'
            elif all(folio.state == 'invoiced' for folio in booking.folio_ids):
                booking.folio_status = 'invoiced'
            else:
                booking.folio_status = 'open'

    def action_create_folio(self):
        """Manual recovery path: if a folio was deleted (only a Manager can - see
        hostel.folio.unlink()'s guard against deleting an invoiced one, staff can't delete any
        folio at all per ACL) while the booking is still checked in/out, this re-creates one
        with a fresh stay line so the stay can still be billed."""
        for booking in self:
            if booking.state not in ('checked_in', 'checked_out'):
                raise UserError("Only a checked-in or checked-out booking can have a folio.")
            booking._create_folio()

    def action_view_folios(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Folio',
            'res_model': 'hostel.folio',
            'context': {'default_booking_id': self.id},
        }
        if len(self.folio_ids) == 1:
            action.update(res_id=self.folio_ids.id, view_mode='form')
        else:
            action.update(view_mode='list,form', domain=[('booking_id', '=', self.id)])
        return action

    @api.depends('check_in_date', 'check_out_date')
    def _compute_nights(self):
        for booking in self:
            if booking.check_in_date and booking.check_out_date and booking.check_out_date > booking.check_in_date:
                booking.nights = (booking.check_out_date - booking.check_in_date).days
            else:
                booking.nights = 0

    @api.depends('nights', 'rate')
    def _compute_total_price(self):
        for booking in self:
            booking.total_price = booking.nights * booking.rate

    @api.depends('booking_unit', 'room_id.room_type_id', 'bed_id.room_id.room_type_id')
    def _compute_room_type_id(self):
        for booking in self:
            if booking.booking_unit == 'room':
                booking.room_type_id = booking.room_id.room_type_id
            else:
                booking.room_type_id = booking.bed_id.room_id.room_type_id

    def _rate_snapshot(self):
        """Compute the nightly rate from the CURRENT rate plan (if set) or room type. Called at
        create and via onchange while editing — never as a reactive compute, so an existing
        booking's rate does not move when the rate plan/room type's rate later changes."""
        self.ensure_one()
        if self.rate_plan_id:
            return self.rate_plan_id.price_per_night
        if self.booking_unit == 'room' and self.room_id:
            return self.room_id.room_type_id.default_rate
        if self.booking_unit == 'bed' and self.bed_id:
            return self.bed_id.room_id.room_type_id.default_rate
        return 0.0

    @api.onchange('booking_unit')
    def _onchange_booking_unit(self):
        if self.booking_unit == 'room':
            self.bed_id = False
        else:
            self.room_id = False

    @api.onchange('booking_unit', 'room_id', 'bed_id')
    def _onchange_reset_rate_plan(self):
        # A rate plan is tied to a room type; changing the booked unit can change the room type
        # out from under a previously-selected plan, so drop it rather than silently keep a
        # rate plan that no longer matches.
        if self.rate_plan_id and self.rate_plan_id.room_type_id != self.room_type_id:
            self.rate_plan_id = False

    @api.onchange('booking_unit', 'room_id', 'bed_id', 'rate_plan_id')
    def _onchange_rate(self):
        self.rate = self._rate_snapshot()

    @api.constrains('booking_unit', 'room_id', 'bed_id')
    def _check_unit_target(self):
        for booking in self:
            if booking.booking_unit == 'room' and not booking.room_id:
                raise ValidationError("A whole-room booking requires a room.")
            if booking.booking_unit == 'bed' and not booking.bed_id:
                raise ValidationError("A single-bed booking requires a bed.")

    @api.constrains('booking_unit', 'room_id', 'bed_id', 'check_in_date', 'check_out_date', 'state')
    def _check_no_overlap(self):
        closed_states = ('cancelled', 'no_show')
        for booking in self:
            if booking.state in closed_states or not (booking.check_in_date and booking.check_out_date):
                continue
            if booking.booking_unit == 'room' and not booking.room_id:
                continue
            if booking.booking_unit == 'bed' and not booking.bed_id:
                continue

            base_domain = [
                ('id', '!=', booking.id),
                ('state', 'not in', closed_states),
                ('check_in_date', '<', booking.check_out_date),
                ('check_out_date', '>', booking.check_in_date),
            ]
            if booking.booking_unit == 'room':
                target_name = booking.room_id.display_name
                domain = base_domain + [
                    '|',
                    ('room_id', '=', booking.room_id.id),
                    ('bed_id.room_id', '=', booking.room_id.id),
                ]
            else:
                target_name = booking.bed_id.display_name
                domain = base_domain + [
                    '|',
                    ('bed_id', '=', booking.bed_id.id),
                    ('room_id', '=', booking.bed_id.room_id.id),
                ]
            conflict = self.search(domain, limit=1)
            if conflict:
                raise ValidationError(
                    "%s is already booked by %s for an overlapping period."
                    % (target_name, conflict.name)
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hostel.booking') or 'New'
        records = super().create(vals_list)
        for booking, vals in zip(records, vals_list):
            if 'rate' not in vals:
                booking.rate = booking._rate_snapshot()
        return records

    def action_confirm(self):
        for booking in self:
            if not booking.check_in_date or not booking.check_out_date or booking.check_out_date <= booking.check_in_date:
                raise UserError("Check-out date must be after the check-in date.")
            if booking.guest_id.is_blacklisted:
                raise UserError(
                    "%s is blacklisted and cannot be confirmed for a new booking.%s"
                    % (booking.guest_id.name, (" Reason: %s" % booking.guest_id.blacklist_reason)
                       if booking.guest_id.blacklist_reason else ""))
            booking.state = 'confirmed'
            # Only a bed-level booking gets a visible hold before check-in: a bed can be
            # `booked`, but hostel.room.state has no equivalent value - a room-level booking
            # relies on the overlap constraint alone until check-in actually occupies it.
            if booking.booking_unit == 'bed' and booking.bed_id:
                booking.bed_id.status = 'booked'
            booking.activity_schedule(
                'mail.mail_activity_data_todo', date_deadline=booking.check_in_date,
                summary='Guest arrival', user_id=self.env.uid)
            # Fresh confirmation, fresh reminder eligibility - relevant on re-confirm after a
            # date change or a no-show/cancel reversal, same reasoning as the checkout flag.
            booking.arrival_reminder_notified = False
            # Silently skip rather than queue a doomed mail.mail with nowhere to deliver - a
            # missing guest email shouldn't block confirming the booking itself.
            if booking.guest_id.email:
                self.env.ref(
                    'guesthouse_management.mail_template_hostel_booking_confirmation'
                ).send_mail(booking.id, force_send=False)

    def action_cancel(self):
        for booking in self:
            if booking.state == 'checked_out':
                raise UserError("A checked-out booking cannot be cancelled.")
            booking._release_unit()
            booking.state = 'cancelled'

    def action_no_show(self):
        for booking in self:
            if booking.state != 'confirmed':
                raise UserError("Only a confirmed booking can be marked as a no-show.")
            booking._release_unit()
            booking.state = 'no_show'

    def action_set_to_draft(self):
        for booking in self:
            booking._release_unit()
            booking.state = 'draft'

    def _release_unit(self):
        """Release any hold this booking placed on its bed/room (booked/occupied -> available),
        and clear any pending arrival/checkout reminder activity. Used whenever a booking leaves
        confirmed/checked_in without going through a normal checkout (cancel, no-show, back to
        draft). Never touches a bed/room that's under maintenance."""
        self.ensure_one()
        self.activity_unlink(['mail.mail_activity_data_todo'])
        if self.booking_unit == 'bed' and self.bed_id and self.bed_id.status != 'maintenance':
            self.bed_id.status = 'available'
            self.bed_id.room_id._sync_state_from_beds()
        elif self.booking_unit == 'room' and self.room_id and self.room_id.state == 'occupied':
            self.room_id.bed_ids.filtered(lambda bed: bed.status != 'maintenance').write({'status': 'available'})
            self.room_id.state = 'available'

    def action_check_in(self):
        for booking in self:
            if booking.state != 'confirmed':
                raise UserError("Only a confirmed booking can be checked in.")
            if booking.deposit_required and not booking.deposit_paid:
                raise UserError(
                    "%s requires a deposit that hasn't been marked as paid yet. Collect it and "
                    "tick Deposit Paid before checking the guest in." % booking.name)
            if booking.booking_unit == 'room' and booking.room_id:
                if booking.room_id.state != 'available':
                    raise UserError(
                        "%s is not available (currently %s)."
                        % (booking.room_id.display_name, booking.room_id.state))
                booking.room_id.bed_ids.write({'status': 'occupied'})
                booking.room_id.state = 'occupied'
            elif booking.booking_unit == 'bed' and booking.bed_id:
                if booking.bed_id.status not in ('available', 'booked'):
                    raise UserError(
                        "%s is not available (currently %s)."
                        % (booking.bed_id.display_name, booking.bed_id.status))
                booking.bed_id.status = 'occupied'
                booking.bed_id.room_id._sync_state_from_beds()
            booking.state = 'checked_in'
            booking._create_folio()
            # Arrival reminder is done; replace it with a checkout reminder for the same booking.
            booking.activity_unlink(['mail.mail_activity_data_todo'])
            booking.activity_schedule(
                'mail.mail_activity_data_todo', date_deadline=booking.check_out_date,
                summary='Guest checkout', user_id=self.env.uid)
            # Fresh stay, fresh reminder eligibility - relevant on re-check-in after a date
            # change, otherwise the popup cron would think today's checkout was already handled.
            booking.checkout_reminder_notified = False
            booking.overstay_reminder_notified = False

    def _create_folio(self):
        """Open this booking's folio with a pre-filled stay line, if it doesn't have one yet.
        Idempotent - safe to call even if a folio somehow already exists (e.g. re-check-in after
        a data fix)."""
        self.ensure_one()
        if self.folio_ids:
            return self.folio_ids[0]
        stay_charge_type = self.env.ref(
            'guesthouse_management.hostel_charge_type_stay', raise_if_not_found=False)
        unit_name = (self.room_id or self.bed_id).display_name
        return self.env['hostel.folio'].create({
            'booking_id': self.id,
            'line_ids': [(0, 0, {
                'charge_type_id': stay_charge_type.id if stay_charge_type else False,
                'description': '%d night(s) x %s' % (self.nights, unit_name),
                'qty': self.nights,
                'unit_price': self.rate,
            })],
        })

    def action_check_out(self):
        for booking in self:
            if booking.state != 'checked_in':
                raise UserError("Only a checked-in booking can be checked out.")
            if booking.booking_unit == 'room' and booking.room_id:
                room = booking.room_id
                room.bed_ids.filtered(lambda bed: bed.status != 'maintenance').write({'status': 'available'})
                room.state = 'available'
                room.housekeeping_status = 'dirty'
            elif booking.booking_unit == 'bed' and booking.bed_id:
                booking.bed_id.status = 'available'
                room = booking.bed_id.room_id
                room._sync_state_from_beds()
                room.housekeeping_status = 'dirty'
            booking.state = 'checked_out'
            booking.activity_unlink(['mail.mail_activity_data_todo'])
            room._create_checkout_task()

    def _notifiable_property_users(self, booking):
        """Staff/Manager users allowed to see this booking, per the same property-scoping
        convention as the module's ir.rules (no properties assigned = unrestricted, not
        "notify about nothing"). Shared by all the front-desk reminder crons below so the
        recipient logic only lives in one place."""
        notifiable = (
            self.env.ref('guesthouse_management.group_hostel_staff').user_ids
            | self.env.ref('guesthouse_management.group_hostel_manager').user_ids
        )
        return notifiable.filtered(
            lambda u: not u.hostel_property_ids or booking.property_id in u.hostel_property_ids)

    @api.model
    def _cron_checkout_reminders(self):
        """Pop a live in-app notification for today's checkouts, on top of the passive
        mail.activity reminder - the activity only shows up if someone goes looking (systray/
        list); this reaches anyone with Odoo open right now. Only reaches connected browser
        sessions (bus/longpolling), so it's not a substitute for the activity if nobody's
        logged in when it fires - both mechanisms stay in place, this one is additive."""
        today = fields.Date.context_today(self)
        bookings = self.search([
            ('state', '=', 'checked_in'),
            ('check_out_date', '=', today),
            ('checkout_reminder_notified', '=', False),
        ])
        for booking in bookings:
            self._notifiable_property_users(booking)._bus_send('simple_notification', {
                'type': 'warning',
                'title': 'Checkout Today',
                'message': '%s: %s is due to check out today.' % (booking.name, booking.guest_id.name),
                'sticky': True,
            })
        bookings.write({'checkout_reminder_notified': True})

    @api.model
    def _cron_overstay_reminders(self):
        """The other half of the checkout story: a guest still checked_in after their
        check_out_date has fully passed. Deliberately alert-only, unlike _cron_auto_no_show -
        auto-checking someone out would cut a legitimately extended stay short and mess with
        folio billing mid-stay, so this only ever notifies; a human decides whether to check
        them out, extend the booking, or something else entirely."""
        today = fields.Date.context_today(self)
        bookings = self.search([
            ('state', '=', 'checked_in'),
            ('check_out_date', '<', today),
            ('overstay_reminder_notified', '=', False),
        ])
        for booking in bookings:
            self._notifiable_property_users(booking)._bus_send('simple_notification', {
                'type': 'danger',
                'title': 'Overstay',
                'message': '%s: %s was due to check out on %s and has not checked out yet.'
                           % (booking.name, booking.guest_id.name, booking.check_out_date),
                'sticky': True,
            })
        bookings.write({'overstay_reminder_notified': True})

    @api.model
    def _cron_arrival_reminders(self):
        """Same live-popup mechanism as _cron_checkout_reminders, for today's arrivals -
        front desk should know a guest is expected today at least as reliably as knowing one is
        due to leave."""
        today = fields.Date.context_today(self)
        bookings = self.search([
            ('state', '=', 'confirmed'),
            ('check_in_date', '=', today),
            ('arrival_reminder_notified', '=', False),
        ])
        for booking in bookings:
            self._notifiable_property_users(booking)._bus_send('simple_notification', {
                'type': 'info',
                'title': 'Arrival Today',
                'message': '%s: %s is expected to arrive today.' % (booking.name, booking.guest_id.name),
                'sticky': True,
            })
        bookings.write({'arrival_reminder_notified': True})

    @api.model
    def _cron_auto_no_show(self):
        """Confirmed bookings nobody checked in by the end of their check-in date are marked
        no_show automatically, freeing the room/bed instead of leaving it silently blocked
        forever waiting for staff to notice and click the button by hand. Deliberately
        date-only (not time-of-day, despite hostel.property.check_in_time/check_out_time
        existing) to match the rest of the booking model, which reasons in whole days
        everywhere else (overlap checks, pricing, nights) - a full day's grace before calling
        it a no-show, no per-property fine-tuning. Revisit if that ever proves too coarse."""
        today = fields.Date.context_today(self)
        bookings = self.search([
            ('state', '=', 'confirmed'),
            ('check_in_date', '<', today),
        ])
        for booking in bookings:
            recipients = self._notifiable_property_users(booking)
            booking.action_no_show()
            recipients._bus_send('simple_notification', {
                'type': 'danger',
                'title': 'Auto No-show',
                'message': '%s: %s never checked in and was automatically marked as a no-show.'
                           % (booking.name, booking.guest_id.name),
                'sticky': True,
            })

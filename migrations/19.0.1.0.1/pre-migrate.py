# -*- coding: utf-8 -*-
def migrate(cr, version):
    # hostel.folio.state's 'paid' value was removed - payment status is now conveyed live via
    # payment_state (related from invoice_id) instead of a separate stored state value that had
    # to be kept in sync by hand. Any folio row still holding the old 'paid' string reads back as
    # its closest remaining valid state; payment_state already reflects the real paid/not-paid fact.
    cr.execute("UPDATE hostel_folio SET state = 'invoiced' WHERE state = 'paid'")

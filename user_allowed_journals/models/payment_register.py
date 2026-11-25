# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.fields import Command

class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.depends("payment_type", "company_id", "can_edit_wizard")
    def _compute_available_journal_ids(self):
        """Robust override:
        - Call super() to keep Odoo's internal logic (which varies by version/edition).
        - If current user configured Allowed Journals, intersect them with computed available journals.
        """
        super()._compute_available_journal_ids()

        user_allowed = self.env.user.allowed_journal_ids
        if not user_allowed:
            return

        for wizard in self:
            allowed_company = user_allowed.filtered(lambda j: j.company_id == wizard.company_id)
            allowed = allowed_company or user_allowed
            wizard.available_journal_ids = user_allowed.ids

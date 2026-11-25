# -*- coding: utf-8 -*-
from odoo import models, fields

class ResUsers(models.Model):
    _inherit = "res.users"

    allowed_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        relation="res_users_allowed_journal_rel",
        column1="user_id",
        column2="journal_id",
        string="Allowed Journals",
        domain="[('company_id', 'in', allowed_company_ids)]",
        help="If set, payment/register wizards will only show journals from this list (after applying standard filters).",
    )

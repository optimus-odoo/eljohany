from odoo import models
from odoo.tools.sql import create_index


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def init(self):
        super().init()
        # The standard ledger index starts with account_id.  This partial index
        # gives PostgreSQL an efficient path when a branch filter is selected,
        # while avoiding index entries for legacy rows without a branch.
        create_index(
            self.env.cr,
            indexname='account_move_line_branch_account_date_idx',
            tablename='account_move_line',
            expressions=['branch_id', 'account_id', 'date'],
            where='branch_id IS NOT NULL',
        )

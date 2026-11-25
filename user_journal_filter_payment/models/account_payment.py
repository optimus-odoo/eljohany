from odoo import models, api

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.depends('payment_type')
    def _compute_available_journal_ids(self):
        for pay in self:
            domain = [
                '|',
                ('company_id', 'parent_of', self.env.company.id),
                ('company_id', 'child_of', self.env.company.id),
                ('type', 'in', ('bank', 'cash', 'credit')),
            ]

            if self.env.user.allowed_journal_ids:
                domain.append(('id', 'in', self.env.user.allowed_journal_ids.ids))

            journals = self.env['account.journal'].search(domain)

            if pay.payment_type == 'inbound':
                journals = journals.filtered('inbound_payment_method_line_ids')
            else:
                journals = journals.filtered('outbound_payment_method_line_ids')

            pay.available_journal_ids = journals

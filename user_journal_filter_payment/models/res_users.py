from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_journal_ids = fields.Many2many(
        'account.journal',
        string='Payments Allowed Journals'
    )

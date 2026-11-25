
from odoo import models, fields, _
from odoo.exceptions import UserError

class AdjustmentPasswordWizard(models.TransientModel):
    _name = 'adjustment.password.wizard'
    _description = 'Adjustment Password Wizard'

    password = fields.Char(required=True)

    def action_confirm_password(self):
        correct = self.env['ir.config_parameter'].sudo().get_param('adjustment_apply_password.password', '1234')

        if self.password != correct:
            raise UserError("Wrong Password")

        records = self.env[self.env.context.get('active_model')].browse(self.env.context.get('active_ids'))
        return records.with_context(skip_adjustment_password=True).action_apply_inventory()

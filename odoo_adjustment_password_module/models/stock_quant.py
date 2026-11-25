
from odoo import models

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def action_apply_inventory(self):
        if not self.env.context.get('skip_adjustment_password'):
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'adjustment.password.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'active_model': self._name,
                    'active_ids': self.ids,
                }
            }
        return super().action_apply_inventory()

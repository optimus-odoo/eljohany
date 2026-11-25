from odoo import models, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            user = line.order_id.user_id
            if user and user.default_analytic_account_id and not line.analytic_distribution:
                line.analytic_distribution = {
                    str(user.default_analytic_account_id.id): 100
                }
        return lines

    @api.onchange('product_id')
    def _onchange_product_set_analytic(self):
        for line in self:
            user = line.order_id.user_id
            if user and user.default_analytic_account_id and not line.analytic_distribution:
                line.analytic_distribution = {
                    str(user.default_analytic_account_id.id): 100
                }
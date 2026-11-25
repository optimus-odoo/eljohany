from odoo import api, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.onchange("company_id")
    def _onchange_company_id_allowed_warehouse(self):
        user = self.env.user

        allowed_whs = user.allowed_warehouse_ids.filtered(
            lambda w: w.company_id == self.company_id
        )

        if not allowed_whs and self.company_id:
            allowed_whs = self.env["stock.warehouse"].search(
                [("company_id", "=", self.company_id.id)]
            )

        return {
            "domain": {
                "warehouse_id": [("id", "in", allowed_whs.ids)]
            }
        }

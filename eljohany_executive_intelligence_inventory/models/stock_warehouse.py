from odoo import api, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        if not self.env.context.get("_ei_skip_automatic_setup"):
            self.env["res.users"].with_context(
                _ei_skip_automatic_setup=True
            )._ei_setup_all_defaults()
        return warehouses

    def write(self, vals):
        result = super().write(vals)
        if (
            "company_id" in vals
            and not self.env.context.get("_ei_skip_automatic_setup")
        ):
            self.env["res.users"].with_context(
                _ei_skip_automatic_setup=True
            )._ei_setup_all_defaults()
        return result

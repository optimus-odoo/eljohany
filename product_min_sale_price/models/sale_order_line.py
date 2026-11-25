from odoo import models, api, _
from odoo.exceptions import ValidationError

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.onchange("price_unit", "product_id")
    def _onchange_price_unit_range(self):
        for line in self:
            if not line.product_id:
                continue

            if self.env.user.has_group(
                "product_min_sale_price.group_ignore_min_price_warning"
            ):
                continue

            tmpl = line.product_id.product_tmpl_id
            price = line.price_unit

            if tmpl.min_cost and price < tmpl.min_cost:
                return {
                    "warning": {
                        "title": _("Warning"),
                        "message": _(
                            "Unit price (%s) is lower than the minimum allowed price (%s)"
                        ) % (price, tmpl.min_cost),
                    }
                }

            # if tmpl.min_cost and price < tmpl.max_cost:
            #     return {
            #         "warning": {
            #             "title": _("Warning"),
            #             "message": _(
            #                 "Unit price (%s) is higher than the maximum allowed price (%s)"
            #             ) % (price, tmpl.max_cost),
            #         }
            #     }

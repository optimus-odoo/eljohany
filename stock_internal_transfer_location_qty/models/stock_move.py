
from odoo import api, fields, models

class StockMove(models.Model):
    _inherit = "stock.move"

    location_qty = fields.Html(string="Location Quantity", readonly=True)

    @api.onchange("product_id", "location_id", "picking_type_id")
    def _onchange_product_id_internal_transfer(self):
        for move in self:
            move.location_qty = ""
            if not move.product_id:
                continue
            if not move.picking_type_id or move.picking_type_id.code != "internal":
                continue

            quants = self.env["stock.quant"].search([
                ("product_id", "=", move.product_id.id),
                ("location_id.usage", "=", "internal"),
            ])

            lines = []
            for q in quants:
                if q.quantity > 0:
                    lines.append(
                        f"<p><b>📍 {q.location_id.complete_name}:</b> "
                        f"<span style='color:blue;'>{q.quantity}</span></p>"
                    )
            move.location_qty = "".join(lines)

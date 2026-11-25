from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosOrder(models.Model):
    _inherit = "pos.order"

    order_type = fields.Selection(
        selection=[
            ("dine_in", "محلي"),
            ("takeaway", "سفري"),
        ],
        string="نوع الطلب",
        copy=False,
        readonly=True,
        index=True,
    )

    @api.model
    def _order_fields(self, ui_order):
        values = super()._order_fields(ui_order)
        order_type = ui_order.get("order_type")
        if order_type not in dict(self._fields["order_type"].selection):
            raise ValidationError(
                _("يجب اختيار محلي أو سفري قبل اعتماد طلب نقطة البيع.")
            )
        values["order_type"] = order_type
        return values

    def _export_for_ui(self, order):
        values = super()._export_for_ui(order)
        values.update(
            {
                "order_type": order.order_type or False,
                "receipt_number": order.name or order.pos_reference,
                "pos_config_name": order.config_id.name or False,
                "pos_session_name": order.session_id.name or False,
            }
        )
        return values

    @api.model
    def create_from_ui(self, orders, draft=False):
        """Return the server receipt sequence to the POS before first printing."""
        result = super().create_from_ui(orders, draft=draft)
        records_by_id = {
            order.id: order
            for order in self.browse(
                [item["id"] for item in result if item.get("id")]
            ).exists()
        }
        for item in result:
            order = records_by_id.get(item.get("id"))
            if order:
                item["receipt_number"] = order.name or order.pos_reference
        return result


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    receipt_name_ar = fields.Char(
        string="Arabic Receipt Product Name",
        readonly=True,
        copy=False,
    )
    receipt_name_en = fields.Char(
        string="English Receipt Product Name",
        readonly=True,
        copy=False,
    )

    @api.model
    def _translated_receipt_product_name(self, product, lang):
        language = self.env["res.lang"].with_context(active_test=False).search(
            [("code", "=", lang)], limit=1
        )
        name_context = {"display_default_code": False}
        if language.active:
            name_context["lang"] = lang
        return product.with_context(**name_context).display_name

    def _order_line_fields(self, line, session_id=None):
        if line and line[2].get("product_id"):
            values = line[2]
            product_id = values["product_id"]
            if isinstance(product_id, (list, tuple)):
                product_id = product_id[0]
            product = self.env["product.product"].browse(product_id).exists()
            if product:
                if not values.get("receipt_name_ar"):
                    values["receipt_name_ar"] = (
                        self._translated_receipt_product_name(product, "ar_001")
                    )
                if not values.get("receipt_name_en"):
                    values["receipt_name_en"] = (
                        self._translated_receipt_product_name(product, "en_US")
                    )
        return super()._order_line_fields(line, session_id=session_id)

    def _export_for_ui(self, orderline):
        values = super()._export_for_ui(orderline)
        product = orderline.product_id
        fallback = orderline.full_product_name or product.display_name
        values.update(
            {
                "receipt_name_ar": orderline.receipt_name_ar
                or self._translated_receipt_product_name(product, "ar_001")
                or fallback,
                "receipt_name_en": orderline.receipt_name_en
                or self._translated_receipt_product_name(product, "en_US")
                or fallback,
            }
        )
        return values

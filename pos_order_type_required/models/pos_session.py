from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _get_pos_receipt_product_names(self, product_ids, lang):
        language = self.env["res.lang"].with_context(active_test=False).search(
            [("code", "=", lang)], limit=1
        )
        name_context = {"display_default_code": False}
        if language.active:
            name_context["lang"] = lang
        products = self.env["product.product"].with_context(
            **name_context
        ).browse(product_ids).exists()
        return {product.id: product.display_name for product in products}

    def _process_pos_ui_product_product(self, products):
        """Add both receipt languages without changing the POS display language."""
        super()._process_pos_ui_product_product(products)
        product_ids = [values["id"] for values in products if values.get("id")]
        if not product_ids:
            return

        arabic_names = self._get_pos_receipt_product_names(product_ids, "ar_001")
        english_names = self._get_pos_receipt_product_names(product_ids, "en_US")
        for values in products:
            product_id = values.get("id")
            fallback = values.get("display_name") or values.get("name") or ""
            values["receipt_name_ar"] = arabic_names.get(product_id) or fallback
            values["receipt_name_en"] = english_names.get(product_id) or fallback

    def _loader_params_res_company(self):
        """Expose all company fields required by the branded POS receipt."""
        params = super()._loader_params_res_company()
        fields_to_load = params["search_params"]["fields"]
        for field_name in (
            "street",
            "street2",
            "city",
            "zip",
            "pos_receipt_use_alias",
            "pos_receipt_alias",
        ):
            if field_name not in fields_to_load:
                fields_to_load.append(field_name)
        return params

from odoo import fields, models

from .audit_utils import create_log_entries, prepare_values


class ProductProduct(models.Model):
    _inherit = "product.product"

    variant_change_log_ids = fields.One2many(
        "eljohany.product.audit.log",
        "product_id",
        string="Variant Change Log",
        groups="eljohany_product_audit_log.group_product_audit_viewer",
        readonly=True,
        copy=False,
    )

    def write(self, vals):
        if self.env.context.get("_product_audit_from_template"):
            return super().write(vals)

        before_values = prepare_values(self, vals, skip_template_related=True)
        result = super().write(vals)
        create_log_entries(self, before_values, "product.product")
        return result

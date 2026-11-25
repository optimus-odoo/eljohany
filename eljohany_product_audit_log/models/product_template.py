from odoo import fields, models

from .audit_utils import create_log_entries, prepare_values


class ProductTemplate(models.Model):
    _inherit = "product.template"

    change_log_ids = fields.One2many(
        "eljohany.product.audit.log",
        "product_tmpl_id",
        string="Change Log",
        groups="eljohany_product_audit_log.group_product_audit_viewer",
        readonly=True,
        copy=False,
    )

    def write(self, vals):
        before_values = prepare_values(self, vals)
        records_for_write = self.with_context(_product_audit_from_template=True)
        result = super(ProductTemplate, records_for_write).write(vals)
        create_log_entries(self, before_values, "product.template")
        return result

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class ProductAuditLog(models.Model):
    _name = "eljohany.product.audit.log"
    _description = "Product Change Log"
    _order = "changed_on desc, id desc"
    _rec_name = "field_label"

    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product",
        required=True,
        index=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Variant",
        index=True,
        ondelete="set null",
    )
    target_model = fields.Selection(
        [
            ("product.template", "Product Template"),
            ("product.product", "Product Variant"),
        ],
        string="Changed On",
        required=True,
        index=True,
    )
    target_name = fields.Char(string="Record", required=True)
    target_res_id = fields.Integer(string="Record ID", required=True, index=True)
    field_name = fields.Char(string="Technical Field", required=True, index=True)
    field_label = fields.Char(string="Changed Field", required=True)
    field_display_name = fields.Char(
        string="Changed Field",
        compute="_compute_field_display_name",
    )
    old_value = fields.Text(string="Previous Value")
    new_value = fields.Text(string="New Value")
    changed_by_id = fields.Many2one(
        "res.users",
        string="Changed By",
        required=True,
        index=True,
        ondelete="restrict",
    )
    changed_on = fields.Datetime(
        string="Change Date",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    operation_id = fields.Char(string="Operation Reference", required=True, index=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        index=True,
        ondelete="restrict",
    )

    @api.depends("target_model", "field_name", "field_label")
    def _compute_field_display_name(self):
        for log in self:
            model = self.env[log.target_model]
            field = model._fields.get(log.field_name)
            if field:
                description = field.get_description(self.env)
                log.field_display_name = description.get("string") or log.field_label
            else:
                log.field_display_name = log.field_label

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("_product_audit_internal_create"):
            raise AccessError(
                _("Product change log entries can only be created automatically.")
            )
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_("Product change log entries are immutable."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_module_uninstall(self):
        raise AccessError(_("Product change log entries cannot be deleted."))

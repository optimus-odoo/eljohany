from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    partner_dual_account_control_enabled = fields.Boolean(
        string="Enforce Customer and Vendor Account Separation",
        default=False,
        help=(
            "Block invoices, bills, and payments that use a settlement account "
            "outside the partner's configured customer or vendor account path."
        ),
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    partner_dual_account_control_enabled = fields.Boolean(
        related="company_id.partner_dual_account_control_enabled",
        readonly=False,
    )

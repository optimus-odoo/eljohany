from odoo import _, api, fields, models

from .account_policy import (
    PAYABLE_ACCOUNT_TYPE,
    RECEIVABLE_ACCOUNT_TYPE,
    get_account_issues,
    get_direction_account,
)


class ResPartner(models.Model):
    _inherit = "res.partner"

    account_control_state = fields.Selection(
        selection=[
            ("valid", "Valid"),
            ("invalid", "Requires Review"),
        ],
        string="Directional Account Status",
        compute="_compute_account_control_status",
        compute_sudo=True,
    )
    account_control_message = fields.Char(
        string="Directional Account Check",
        compute="_compute_account_control_status",
        compute_sudo=True,
    )

    def _get_directional_account_issues(self, company=None):
        self.ensure_one()
        company = company or self.env.company
        receivable = get_direction_account(self, company, "customer")
        payable = get_direction_account(self, company, "supplier")
        return {
            "customer": get_account_issues(
                receivable, company, RECEIVABLE_ACCOUNT_TYPE
            ),
            "supplier": get_account_issues(
                payable, company, PAYABLE_ACCOUNT_TYPE
            ),
        }

    @api.depends(
        "property_account_receivable_id",
        "property_account_payable_id",
        "commercial_partner_id",
    )
    @api.depends_context("company")
    def _compute_account_control_status(self):
        for partner in self:
            issues = partner._get_directional_account_issues()
            if issues["customer"] or issues["supplier"]:
                partner.account_control_state = "invalid"
                partner.account_control_message = _(
                    "The customer or vendor account requires review for %(company)s.",
                    company=self.env.company.display_name,
                )
            else:
                partner.account_control_state = "valid"
                partner.account_control_message = _(
                    "Customer and vendor accounts are configured independently for %(company)s.",
                    company=self.env.company.display_name,
                )

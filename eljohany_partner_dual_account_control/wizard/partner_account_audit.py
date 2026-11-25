from odoo import _, api, fields, models, Command

from ..models.account_policy import (
    PAYABLE_ACCOUNT_TYPE,
    RECEIVABLE_ACCOUNT_TYPE,
    get_account_issues,
    get_direction_account,
)


ISSUE_LABELS = {
    "missing": "No account is configured.",
    "wrong_type": "The account type does not match the transaction direction.",
    "deprecated": "The account is deprecated.",
    "not_reconcilable": "The account is not reconcilable.",
    "wrong_company": "The account belongs to another company.",
}


class PartnerAccountAuditWizard(models.TransientModel):
    _name = "partner.account.audit.wizard"
    _description = "Partner Directional Account Audit"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Specific Partners",
        help="Leave empty to audit all active customers and vendors.",
    )
    include_archived = fields.Boolean(string="Include Archived Partners")
    show_valid = fields.Boolean(string="Show Valid Accounts")
    line_ids = fields.One2many(
        comodel_name="partner.account.audit.line",
        inverse_name="wizard_id",
        string="Audit Results",
        readonly=True,
    )
    issue_count = fields.Integer(
        string="Issues",
        compute="_compute_issue_count",
    )
    checked_partner_count = fields.Integer(
        string="Partners Checked",
        readonly=True,
    )

    @api.depends("line_ids.issue_type")
    def _compute_issue_count(self):
        for wizard in self:
            wizard.issue_count = len(
                wizard.line_ids.filtered(lambda line: line.issue_type != "valid")
            )

    def _get_partners_to_audit(self):
        self.ensure_one()
        if self.partner_ids:
            partners = self.partner_ids
        else:
            partners = self.env["res.partner"].with_context(
                active_test=not self.include_archived
            ).search(
                [
                    "|",
                    ("customer_rank", ">", 0),
                    ("supplier_rank", ">", 0),
                ]
            )
        return partners.mapped("commercial_partner_id")

    def _prepare_direction_lines(self, partner, direction):
        self.ensure_one()
        expected_type = (
            RECEIVABLE_ACCOUNT_TYPE
            if direction == "customer"
            else PAYABLE_ACCOUNT_TYPE
        )
        account = get_direction_account(
            partner,
            self.company_id,
            direction,
        )
        issues = get_account_issues(
            account,
            self.company_id,
            expected_type,
        )
        if not issues and not self.show_valid:
            return []
        if not issues:
            issues = ["valid"]

        return [
            Command.create(
                {
                    "partner_id": partner.id,
                    "direction": direction,
                    "account_id": account.id,
                    "issue_type": issue,
                    "details": _("The account is valid.")
                    if issue == "valid"
                    else _(ISSUE_LABELS[issue]),
                }
            )
            for issue in issues
        ]

    def action_run_audit(self):
        self.ensure_one()
        partners = self._get_partners_to_audit()
        commands = [Command.clear()]
        for partner in partners:
            for direction in ("customer", "supplier"):
                commands += self._prepare_direction_lines(partner, direction)
        self.line_ids = commands
        self.checked_partner_count = len(partners)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class PartnerAccountAuditLine(models.TransientModel):
    _name = "partner.account.audit.line"
    _description = "Partner Directional Account Audit Line"
    _order = "partner_id, direction, issue_type, id"

    wizard_id = fields.Many2one(
        comodel_name="partner.account.audit.wizard",
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
        required=True,
        readonly=True,
    )
    direction = fields.Selection(
        selection=[
            ("customer", "Customer / Receivable"),
            ("supplier", "Vendor / Payable"),
        ],
        string="Direction",
        required=True,
        readonly=True,
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Configured Account",
        readonly=True,
    )
    issue_type = fields.Selection(
        selection=[
            ("valid", "Valid"),
            ("missing", "Missing Account"),
            ("wrong_type", "Wrong Account Type"),
            ("deprecated", "Deprecated Account"),
            ("not_reconcilable", "Not Reconcilable"),
            ("wrong_company", "Wrong Company"),
        ],
        string="Result",
        required=True,
        readonly=True,
    )
    details = fields.Char(string="Details", readonly=True)

    def action_open_partner(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "res_id": self.partner_id.id,
            "view_mode": "form",
            "target": "current",
        }

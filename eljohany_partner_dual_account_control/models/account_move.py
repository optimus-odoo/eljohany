from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .account_policy import (
    PAYABLE_ACCOUNT_TYPE,
    RECEIVABLE_ACCOUNT_TYPE,
    get_account_issues,
    get_direction_account,
)


class AccountMove(models.Model):
    _inherit = "account.move"

    expected_partner_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Expected Partner Settlement Account",
        compute="_compute_partner_account_control",
        compute_sudo=True,
    )
    partner_account_control_state = fields.Selection(
        selection=[
            ("not_applicable", "Not Applicable"),
            ("disabled", "Control Disabled"),
            ("pending", "Pending Journal Items"),
            ("valid", "Valid"),
            ("invalid", "Invalid Configuration"),
            ("mismatch", "Account Mismatch"),
        ],
        string="Partner Account Control",
        compute="_compute_partner_account_control",
        compute_sudo=True,
    )

    def _get_partner_account_direction(self):
        self.ensure_one()
        if self.is_sale_document(include_receipts=True):
            return "customer", RECEIVABLE_ACCOUNT_TYPE
        if self.is_purchase_document(include_receipts=True):
            return "supplier", PAYABLE_ACCOUNT_TYPE
        return False, False

    def _get_expected_partner_account(self):
        self.ensure_one()
        direction, _account_type = self._get_partner_account_direction()
        if not direction:
            return self.env["account.account"]
        return get_direction_account(
            self.commercial_partner_id or self.partner_id,
            self.company_id,
            direction,
            fiscal_position=self.fiscal_position_id,
        )

    @api.depends(
        "partner_id",
        "commercial_partner_id",
        "company_id",
        "company_id.partner_dual_account_control_enabled",
        "move_type",
        "fiscal_position_id",
        "line_ids.account_id",
        "line_ids.display_type",
    )
    def _compute_partner_account_control(self):
        for move in self:
            direction, expected_type = move._get_partner_account_direction()
            if not direction:
                move.expected_partner_account_id = False
                move.partner_account_control_state = "not_applicable"
                continue

            expected_account = move._get_expected_partner_account()
            move.expected_partner_account_id = expected_account
            if not move.company_id.partner_dual_account_control_enabled:
                move.partner_account_control_state = "disabled"
                continue
            issues = get_account_issues(
                expected_account, move.company_id, expected_type
            )
            if issues:
                move.partner_account_control_state = "invalid"
                continue

            term_lines = move.line_ids.filtered(
                lambda line: line.display_type == "payment_term"
            )
            if not term_lines:
                move.partner_account_control_state = "pending"
            elif any(
                line.account_id != expected_account for line in term_lines
            ):
                move.partner_account_control_state = "mismatch"
            else:
                move.partner_account_control_state = "valid"

    def _validate_partner_account_control(self):
        for move in self:
            if not move.company_id.partner_dual_account_control_enabled:
                continue
            direction, expected_type = move._get_partner_account_direction()
            if not direction:
                continue

            expected_account = move._get_expected_partner_account()
            issues = get_account_issues(
                expected_account, move.company_id, expected_type
            )
            if issues:
                raise ValidationError(
                    _(
                        "The %(direction)s settlement account for %(partner)s is not valid for company %(company)s.",
                        direction=_("customer") if direction == "customer" else _("vendor"),
                        partner=move.commercial_partner_id.display_name,
                        company=move.company_id.display_name,
                    )
                )

            term_lines = move.line_ids.filtered(
                lambda line: line.display_type == "payment_term"
            )
            if not term_lines:
                raise ValidationError(
                    _(
                        "No receivable or payable journal item was generated for %(document)s.",
                        document=move.display_name,
                    )
                )
            mismatched_lines = term_lines.filtered(
                lambda line: line.account_id != expected_account
            )
            if mismatched_lines:
                raise ValidationError(
                    _(
                        "The partner settlement account on %(document)s must be %(account)s.",
                        document=move.display_name,
                        account=expected_account.display_name,
                    )
                )

    def action_post(self):
        self._validate_partner_account_control()
        result = super().action_post()
        self._validate_partner_account_control()
        return result

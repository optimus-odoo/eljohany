from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .account_policy import (
    PAYABLE_ACCOUNT_TYPE,
    RECEIVABLE_ACCOUNT_TYPE,
    get_account_issues,
    get_direction_account,
)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    expected_destination_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Expected Payment Settlement Account",
        compute="_compute_destination_account_control",
        compute_sudo=True,
    )
    destination_account_control_state = fields.Selection(
        selection=[
            ("not_applicable", "Not Applicable"),
            ("disabled", "Control Disabled"),
            ("pending", "Pending Destination Account"),
            ("valid", "Valid"),
            ("open_document", "Matches Partner Document"),
            ("invalid", "Invalid Configuration"),
            ("mismatch", "Account Mismatch"),
        ],
        string="Payment Account Control",
        compute="_compute_destination_account_control",
        compute_sudo=True,
    )

    def _get_directional_account_policy(self):
        self.ensure_one()
        if self.partner_type == "customer":
            return "customer", RECEIVABLE_ACCOUNT_TYPE
        if self.partner_type == "supplier":
            return "supplier", PAYABLE_ACCOUNT_TYPE
        return False, False

    @api.depends(
        "partner_id",
        "partner_type",
        "company_id",
        "company_id.partner_dual_account_control_enabled",
        "is_internal_transfer",
        "destination_account_id",
    )
    def _compute_destination_account_control(self):
        for payment in self:
            direction, expected_type = payment._get_directional_account_policy()
            if payment.is_internal_transfer or not payment.partner_id or not direction:
                payment.expected_destination_account_id = False
                payment.destination_account_control_state = "not_applicable"
                continue

            expected_account = get_direction_account(
                payment.partner_id,
                payment.company_id,
                direction,
            )
            payment.expected_destination_account_id = expected_account
            if not payment.company_id.partner_dual_account_control_enabled:
                payment.destination_account_control_state = "disabled"
                continue
            if get_account_issues(
                expected_account,
                payment.company_id,
                expected_type,
            ):
                payment.destination_account_control_state = "invalid"
                continue
            if not payment.destination_account_id:
                payment.destination_account_control_state = "pending"
                continue
            if get_account_issues(
                payment.destination_account_id,
                payment.company_id,
                expected_type,
            ):
                payment.destination_account_control_state = "invalid"
            elif payment.destination_account_id == expected_account:
                payment.destination_account_control_state = "valid"
            elif payment._destination_matches_partner_document(direction):
                payment.destination_account_control_state = "open_document"
            else:
                payment.destination_account_control_state = "mismatch"

    def _destination_matches_open_document(self, direction):
        self.ensure_one()
        move_types = (
            ("out_invoice", "out_refund", "out_receipt")
            if direction == "customer"
            else ("in_invoice", "in_refund", "in_receipt")
        )
        commercial_partner = self.partner_id.commercial_partner_id
        return bool(
            self.env["account.move.line"].search_count(
                [
                    ("partner_id", "child_of", commercial_partner.id),
                    ("company_id", "=", self.company_id.id),
                    ("parent_state", "=", "posted"),
                    ("move_id.move_type", "in", move_types),
                    ("display_type", "=", "payment_term"),
                    ("account_id", "=", self.destination_account_id.id),
                    ("reconciled", "=", False),
                ],
                limit=1,
            )
        )

    def _destination_matches_reconciled_document(self, direction):
        self.ensure_one()
        move_types = (
            ("out_invoice", "out_refund", "out_receipt")
            if direction == "customer"
            else ("in_invoice", "in_refund", "in_receipt")
        )
        payment_lines = self.move_id.line_ids.filtered(
            lambda line: line.account_id == self.destination_account_id
        )
        matched_lines = (
            payment_lines.matched_debit_ids.debit_move_id
            | payment_lines.matched_credit_ids.credit_move_id
        )
        commercial_partner = self.partner_id.commercial_partner_id
        return bool(
            matched_lines.filtered(
                lambda line: (
                    line.account_id == self.destination_account_id
                    and line.move_id.move_type in move_types
                    and line.partner_id.commercial_partner_id
                    == commercial_partner
                )
            )
        )

    def _destination_matches_partner_document(self, direction):
        self.ensure_one()
        return self._destination_matches_open_document(
            direction
        ) or self._destination_matches_reconciled_document(direction)

    def _validate_directional_destination_account(self):
        for payment in self:
            if (
                not payment.company_id.partner_dual_account_control_enabled
                or payment.is_internal_transfer
                or not payment.partner_id
            ):
                continue
            direction, expected_type = payment._get_directional_account_policy()
            if not direction:
                continue

            expected_account = get_direction_account(
                payment.partner_id,
                payment.company_id,
                direction,
            )
            issues = get_account_issues(
                expected_account, payment.company_id, expected_type
            )
            if issues:
                raise ValidationError(
                    _(
                        "The settlement account for %(partner)s is not valid for company %(company)s.",
                        partner=payment.partner_id.display_name,
                        company=payment.company_id.display_name,
                    )
                )
            destination_issues = get_account_issues(
                payment.destination_account_id,
                payment.company_id,
                expected_type,
            )
            if destination_issues:
                raise ValidationError(
                    _(
                        "The destination account on the payment is not a valid %(direction)s account.",
                        direction=_("receivable")
                        if direction == "customer"
                        else _("payable"),
                    )
                )
            if (
                payment.destination_account_id != expected_account
                and not payment._destination_matches_partner_document(direction)
            ):
                raise ValidationError(
                    _(
                        "The payment account for %(partner)s must be %(account)s or match a document for that partner.",
                        partner=payment.partner_id.display_name,
                        account=expected_account.display_name,
                    )
                )

    def action_post(self):
        self._validate_directional_destination_account()
        result = super().action_post()
        self._validate_directional_destination_account()
        return result

# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HrLoanWorkflowStep(models.Model):
    _inherit = "hr.loan.workflow.step"

    step_type = fields.Selection(
        selection_add=[("accounting", "Accounting and Journal Entry")],
        ondelete={"accounting": "set default"},
    )

    @api.constrains("workflow_id", "sequence", "step_type")
    def _check_accounting_step_is_unique_and_last(self):
        accounting_group = self.env.ref("account.group_account_user")
        manager_group = self.env.ref("account.group_account_manager")
        for workflow in self.mapped("workflow_id"):
            accounting_steps = workflow.step_ids.filtered(
                lambda step: step.step_type == "accounting"
            )
            if len(accounting_steps) > 1:
                raise ValidationError(
                    _("A loan workflow can contain only one accounting step.")
                )
            if accounting_steps:
                approver = accounting_steps.approver_id.sudo()
                if (
                    accounting_group not in approver.groups_id
                    and manager_group not in approver.groups_id
                ):
                    raise ValidationError(
                        _(
                            "The user responsible for the accounting step must have "
                            "accounting access."
                        )
                    )
                ordered_steps = workflow.step_ids.sorted(
                    lambda step: (step.sequence, step.id)
                )
                if ordered_steps[-1] != accounting_steps[0]:
                    raise ValidationError(
                        _("The accounting and journal entry step must be the final step.")
                    )


class HrLoanApprovalLine(models.Model):
    _inherit = "hr.loan.approval.line"

    step_type = fields.Selection(
        selection_add=[("accounting", "Accounting and Journal Entry")],
        ondelete={"accounting": "set default"},
    )


class HrLoanAcc(models.Model):
    _inherit = "hr.loan"

    employee_account_id = fields.Many2one(
        "account.account",
        string="Debit Account",
        help="Receivable or employee loan account debited when the loan is disbursed.",
        check_company=True,
        groups="account.group_account_user",
    )
    treasury_account_id = fields.Many2one(
        "account.account",
        string="Credit Account",
        help="Treasury or bank account credited when the loan is disbursed.",
        check_company=True,
        groups="account.group_account_user",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Accounting Journal",
        help="Journal used to post the loan disbursement.",
        check_company=True,
        groups="account.group_account_user",
    )
    loan_move_id = fields.Many2one(
        "account.move",
        string="Loan Journal Entry",
        readonly=True,
        copy=False,
        check_company=True,
        groups="account.group_account_user",
    )

    def _workflow_for_company(self):
        workflow = super()._workflow_for_company()
        accounting_steps = workflow.step_ids.filtered(
            lambda step: step.step_type == "accounting"
        )
        if len(accounting_steps) != 1:
            raise ValidationError(
                _(
                    "The active workflow for company '%s' must contain one final "
                    "accounting and journal entry step.",
                    self.company_id.display_name,
                )
            )
        ordered_steps = workflow.step_ids.sorted(
            lambda step: (step.sequence, step.id)
        )
        if ordered_steps[-1] != accounting_steps[0]:
            raise ValidationError(
                _("The accounting and journal entry step must be the final step.")
            )
        return workflow

    def _workflow_validate_step(self, approval_line):
        result = super()._workflow_validate_step(approval_line)
        if approval_line.step_type != "accounting":
            return result
        contract = self.env["hr.contract"].sudo().search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not contract:
            raise UserError(_("You must define a contract for the employee."))
        if (
            not self.employee_account_id
            or not self.treasury_account_id
            or not self.journal_id
        ):
            raise UserError(
                _(
                    "Select the debit account, credit account, and journal before "
                    "approving the accounting step."
                )
            )
        if not self.loan_lines:
            self.with_context(
                loan_workflow_action=True
            ).action_compute_installment()
        return result

    def _workflow_after_step_approved(self, approval_line):
        result = super()._workflow_after_step_approved(approval_line)
        if approval_line.step_type == "accounting":
            self._create_loan_disbursement_move()
        return result

    def _create_loan_disbursement_move(self):
        for loan in self:
            if loan.loan_move_id:
                raise UserError(
                    _("A journal entry has already been created for this loan.")
                )
            move = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "ref": loan.name,
                    "journal_id": loan.journal_id.id,
                    "date": fields.Date.context_today(loan),
                    "company_id": loan.company_id.id,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": _("Loan for %s") % loan.employee_id.name,
                                "account_id": loan.employee_account_id.id,
                                "partner_id": loan.employee_id.work_contact_id.id,
                                "debit": loan.loan_amount,
                                "credit": 0.0,
                                "loan_id": loan.id,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": _("Loan for %s") % loan.employee_id.name,
                                "account_id": loan.treasury_account_id.id,
                                "partner_id": loan.employee_id.work_contact_id.id,
                                "debit": 0.0,
                                "credit": loan.loan_amount,
                                "loan_id": loan.id,
                            },
                        ),
                    ],
                }
            )
            move.action_post()
            loan.with_context(loan_workflow_action=True).write(
                {"loan_move_id": move.id}
            )
        return True

    def write(self, vals):
        accounting_fields = {
            "employee_account_id",
            "treasury_account_id",
            "journal_id",
        }
        if (
            set(vals)
            and set(vals).issubset(accounting_fields | {"rejection_reason"})
            and not self._is_loan_manager()
        ):
            for loan in self:
                if (
                    loan.state != "waiting_approval_1"
                    or loan.current_approver_id != self.env.user
                    or loan.current_step_type != "accounting"
                ):
                    raise AccessError(
                        _(
                            "Only the user assigned to the current accounting step "
                            "can enter loan accounts."
                        )
                    )
            return super(
                HrLoanAcc, self.with_context(loan_workflow_action=True)
            ).write(vals)
        return super().write(vals)

    def action_double_approve(self):
        return self.action_workflow_approve()


class HrLoanLineAcc(models.Model):
    _inherit = "hr.loan.line"

    payment_move_id = fields.Many2one(
        "account.move",
        string="Installment Journal Entry",
        readonly=True,
        copy=False,
        groups="account.group_account_user",
        check_company=True,
    )

    def action_paid_amount(self, month):
        if not self.env.user.has_group("hr_payroll.group_hr_payroll_user"):
            raise AccessError(
                _("Only an authorized payroll user can post loan installments.")
            )
        for line in self:
            if line.loan_id.state != "approve":
                raise UserError(_("The loan request must be approved."))
            loan = line.loan_id
            payment_move = line.sudo().payment_move_id
            if payment_move and payment_move.state != "cancel":
                raise UserError(
                    _("A journal entry already exists for this loan installment.")
                )
            if not loan.journal_id:
                raise UserError(_("The loan journal is not configured."))
            move = self.env["account.move"].sudo().create(
                {
                    "move_type": "entry",
                    "ref": loan.name,
                    "journal_id": loan.journal_id.id,
                    "date": fields.Date.context_today(line),
                    "company_id": loan.company_id.id,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": _(
                                    "LOAN/%(employee)s/%(month)s",
                                    employee=line.employee_id.name,
                                    month=month,
                                ),
                                "account_id": loan.treasury_account_id.id,
                                "partner_id": line.employee_id.work_contact_id.id,
                                "debit": line.amount,
                                "credit": 0.0,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": _(
                                    "LOAN/%(employee)s/%(month)s",
                                    employee=line.employee_id.name,
                                    month=month,
                                ),
                                "account_id": loan.employee_account_id.id,
                                "partner_id": line.employee_id.work_contact_id.id,
                                "debit": 0.0,
                                "credit": line.amount,
                            },
                        ),
                    ],
                }
            )
            move.action_post()
            line.sudo().payment_move_id = move.id
        return True

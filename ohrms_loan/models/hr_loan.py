# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HrLoanWorkflow(models.Model):
    _name = "hr.loan.workflow"
    _description = "Loan Approval Workflow"
    _order = "company_id, name"

    name = fields.Char(string="Workflow Name", required=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True, ondelete="cascade"
    )
    active = fields.Boolean(default=True)
    step_ids = fields.One2many(
        "hr.loan.workflow.step", "workflow_id", string="Approval Steps", copy=True
    )

    @api.constrains("company_id", "active")
    def _check_one_active_workflow_per_company(self):
        for workflow in self.filtered("active"):
            duplicate = self.search_count(
                [
                    ("id", "!=", workflow.id),
                    ("company_id", "=", workflow.company_id.id),
                    ("active", "=", True),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _("Only one active loan workflow is allowed per company.")
                )


class HrLoanWorkflowStep(models.Model):
    _name = "hr.loan.workflow.step"
    _description = "Loan Approval Workflow Step"
    _order = "sequence, id"

    workflow_id = fields.Many2one(
        "hr.loan.workflow", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        related="workflow_id.company_id", store=True, readonly=True
    )
    sequence = fields.Integer(default=10, required=True)
    name = fields.Char(string="Step Name", required=True)
    approver_id = fields.Many2one(
        "res.users",
        string="Responsible User",
        required=True,
        domain="[('share', '=', False)]",
    )
    step_type = fields.Selection(
        [("approval", "Approval")],
        string="Step Type",
        required=True,
        default="approval",
    )

    @api.constrains("approver_id", "company_id")
    def _check_approver_company(self):
        for step in self:
            if step.company_id not in step.approver_id.company_ids:
                raise ValidationError(
                    _(
                        "The responsible user for step '%(step)s' must have access "
                        "to company '%(company)s'.",
                        step=step.name,
                        company=step.company_id.display_name,
                    )
                )

    def _ensure_approver_group(self):
        group = self.env.ref("ohrms_loan.group_loan_approver")
        for user in self.mapped("approver_id"):
            if group not in user.sudo().groups_id:
                user.sudo().write({"groups_id": [(4, group.id)]})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_approver_group()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "approver_id" in vals:
            self._ensure_approver_group()
        return result


class HrLoanApprovalLine(models.Model):
    _name = "hr.loan.approval.line"
    _description = "Loan Approval History"
    _order = "sequence, id"

    loan_id = fields.Many2one(
        "hr.loan", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        related="loan_id.company_id", store=True, readonly=True
    )
    workflow_step_id = fields.Many2one(
        "hr.loan.workflow.step", ondelete="set null"
    )
    sequence = fields.Integer(string="Sequence", required=True)
    name = fields.Char(string="Step Name", required=True)
    approver_id = fields.Many2one(
        "res.users", string="Responsible User", required=True
    )
    step_type = fields.Selection(
        [("approval", "Approval")],
        string="Step Type",
        required=True,
        default="approval",
        readonly=True,
    )
    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("waiting", "Waiting for Action"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        string="Status",
        required=True,
        readonly=True,
    )
    action_by_id = fields.Many2one("res.users", string="Action By", readonly=True)
    action_date = fields.Datetime(string="Action Date", readonly=True)


class HrLoan(models.Model):
    _name = "hr.loan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Loan Request"
    _order = "date desc, id desc"

    REPEAT_LOAN_WAIT_MONTHS = 6

    @api.model
    def default_get(self, field_list):
        result = super().default_get(field_list)
        user_id = result.get("user_id") or self.env.context.get(
            "user_id", self.env.user.id
        )
        employee = self.env["hr.employee"].sudo().search(
            [("user_id", "=", user_id)], limit=1
        )
        if employee:
            result["employee_id"] = employee.id
            result["company_id"] = employee.company_id.id
            result["currency_id"] = employee.company_id.currency_id.id
        return result

    name = fields.Char(
        string="Loan Name",
        default=lambda self: _("New"),
        readonly=True,
        help="Name of the loan",
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.context_today,
        readonly=True,
        help="Date of the loan request",
    )
    employee_id = fields.Many2one(
        "hr.employee", string="Employee", required=True, help="Employee Name"
    )
    department_id = fields.Many2one(
        "hr.department",
        related="employee_id.department_id",
        readonly=True,
        string="Department",
        help="The department to which the employee belongs.",
    )
    installment = fields.Integer(
        string="No Of Installments", default=1, help="Number of installments"
    )
    payment_date = fields.Date(
        string="Payment Start Date",
        required=True,
        default=fields.Date.context_today,
        help="Date of the payment",
    )
    loan_lines = fields.One2many(
        "hr.loan.line",
        "loan_id",
        string="Loan Line",
        help="Details of installment lines associated with the loan.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        help="Company",
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        help="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    job_position = fields.Many2one(
        "hr.job",
        related="employee_id.job_id",
        readonly=True,
        string="Job Position",
        help="Job position of the employee",
    )
    loan_amount = fields.Monetary(
        string="Loan Amount", required=True, help="Loan amount"
    )
    total_amount = fields.Monetary(
        string="Total Amount",
        store=True,
        readonly=True,
        compute="_compute_total_amount",
        help="The total amount of the loan",
    )
    balance_amount = fields.Monetary(
        string="Balance Amount",
        store=True,
        readonly=True,
        compute="_compute_total_amount",
        help="The remaining balance amount of the loan after deducting the total paid amount.",
    )
    total_paid_amount = fields.Monetary(
        string="Total Paid Amount",
        store=True,
        readonly=True,
        compute="_compute_total_amount",
        help="The total amount that has been paid towards the loan.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting_approval_1", "In Approval"),
            ("waiting_approval_2", "Legacy Accounting Approval"),
            ("approve", "Approved"),
            ("refuse", "Refused"),
            ("cancel", "Canceled"),
        ],
        string="State",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    workflow_id = fields.Many2one(
        "hr.loan.workflow", string="Approval Workflow", readonly=True, copy=False
    )
    approval_line_ids = fields.One2many(
        "hr.loan.approval.line",
        "loan_id",
        string="Approval History",
        readonly=True,
        copy=False,
    )
    current_approval_line_id = fields.Many2one(
        "hr.loan.approval.line", readonly=True, copy=False
    )
    current_approver_id = fields.Many2one(
        related="current_approval_line_id.approver_id",
        string="Current Responsible User",
        store=True,
        readonly=True,
    )
    current_step_name = fields.Char(
        related="current_approval_line_id.name",
        string="Current Approval Stage",
        store=True,
        readonly=True,
    )
    current_step_type = fields.Selection(
        related="current_approval_line_id.step_type",
        string="Current Step Type",
        store=True,
        readonly=True,
    )
    rejection_reason = fields.Text(string="Rejection Reason", copy=False, tracking=True)

    @api.depends("loan_amount", "loan_lines.amount", "loan_lines.paid")
    def _compute_total_amount(self):
        for loan in self:
            total_paid = sum(loan.loan_lines.filtered("paid").mapped("amount"))
            loan.total_amount = loan.loan_amount
            loan.balance_amount = loan.loan_amount - total_paid
            loan.total_paid_amount = total_paid

    @api.constrains("installment", "loan_amount")
    def _check_positive_request_values(self):
        for loan in self:
            if loan.installment <= 0:
                raise ValidationError(
                    _("The number of installments must be greater than zero.")
                )
            if loan.loan_amount <= 0:
                raise ValidationError(_("The loan amount must be greater than zero."))

    def _is_loan_manager(self):
        return self.env.user.has_group("hr.group_hr_user")

    @api.model
    def _get_repeat_loan_eligibility(
        self, employee, reference_date=None, exclude_loan_ids=None
    ):
        """Return the latest unpaid loan and the next permitted request date.

        Fully settled loans keep the existing behavior and do not impose a
        waiting period.  The six-month exception applies only to an approved
        loan whose balance is still outstanding.
        """
        employee.ensure_one()
        reference_date = fields.Date.to_date(
            reference_date or fields.Date.context_today(self)
        )
        domain = [
            ("employee_id", "=", employee.id),
            ("state", "=", "approve"),
            ("balance_amount", ">", 0),
        ]
        if exclude_loan_ids:
            domain.append(("id", "not in", list(exclude_loan_ids)))
        previous_loan = self.sudo().search(
            domain, order="date desc, id desc", limit=1
        )
        if not previous_loan:
            return previous_loan, False, True

        previous_date = fields.Date.to_date(previous_loan.date)
        if not previous_date:
            previous_date = fields.Date.to_date(previous_loan.create_date)
        eligible_date = previous_date + relativedelta(
            months=self.REPEAT_LOAN_WAIT_MONTHS
        )
        return previous_loan, eligible_date, reference_date >= eligible_date

    @api.model
    def _check_repeat_loan_eligibility(
        self, employee, reference_date=None, exclude_loan_ids=None
    ):
        previous_loan, eligible_date, is_eligible = self._get_repeat_loan_eligibility(
            employee,
            reference_date=reference_date,
            exclude_loan_ids=exclude_loan_ids,
        )
        if not is_eligible:
            raise ValidationError(
                _(
                    "Employee %(employee)s has an unpaid approved loan "
                    "%(loan)s. A new loan request is allowed from %(date)s, "
                    "six calendar months after the previous loan request date.",
                    employee=employee.display_name,
                    loan=previous_loan.display_name,
                    date=fields.Date.to_string(eligible_date),
                )
            )
        return True

    def _lock_employee_for_repeat_loan_check(self):
        """Serialize final approvals for each employee to avoid double loans."""
        employee_ids = tuple(self.mapped("employee_id").ids)
        if not employee_ids:
            return
        self.env.cr.execute(
            "SELECT id FROM hr_employee WHERE id IN %s FOR UPDATE",
            [employee_ids],
        )

    @api.model_create_multi
    def create(self, vals_list):
        employee_model = self.env["hr.employee"].sudo()
        for values in vals_list:
            employee = employee_model.browse(values.get("employee_id")).exists()
            if not employee:
                employee = employee_model.search(
                    [("user_id", "=", self.env.user.id)], limit=1
                )
                values["employee_id"] = employee.id
            if not employee:
                raise ValidationError(
                    _("Your user must be linked to an employee before requesting a loan.")
                )
            if not self._is_loan_manager() and employee.user_id != self.env.user:
                raise AccessError(_("You can only create a loan request for yourself."))
            values["company_id"] = employee.company_id.id
            values["currency_id"] = employee.company_id.currency_id.id
            self._check_repeat_loan_eligibility(employee)
            values["name"] = (
                self.env["ir.sequence"].next_by_code("hr.loan.seq") or " "
            )
        return super().create(vals_list)

    def action_compute_installment(self):
        if not self._is_loan_manager() and not self.env.context.get(
            "loan_workflow_action"
        ):
            raise AccessError(
                _("Only loan administrators can calculate installments.")
            )
        for loan in self:
            if loan.state == "approve" and not self.env.context.get(
                "loan_workflow_action"
            ):
                raise UserError(
                    _("Approved loan installments cannot be recalculated.")
                )
            loan.loan_lines.sudo().unlink()
            date_start = datetime.strptime(str(loan.payment_date), "%Y-%m-%d")
            amount = loan.loan_amount / loan.installment
            for _index in range(loan.installment):
                self.env["hr.loan.line"].sudo().create(
                    {
                        "date": date_start,
                        "amount": amount,
                        "employee_id": loan.employee_id.id,
                        "loan_id": loan.id,
                    }
                )
                date_start += relativedelta(months=1)
        return True

    def _check_owner_or_manager(self):
        for loan in self:
            if (
                not self._is_loan_manager()
                and loan.employee_id.user_id != self.env.user
            ):
                raise AccessError(_("You can only manage your own loan requests."))

    def _workflow_for_company(self):
        self.ensure_one()
        workflow = self.env["hr.loan.workflow"].sudo().search(
            [("company_id", "=", self.company_id.id), ("active", "=", True)],
            limit=1,
        )
        if not workflow or not workflow.step_ids:
            raise ValidationError(
                _(
                    "No active loan approval workflow is configured for company '%s'.",
                    self.company_id.display_name,
                )
            )
        return workflow

    def action_submit(self):
        self._check_owner_or_manager()
        for loan in self:
            if loan.state != "draft":
                raise UserError(_("Only draft loan requests can be submitted."))
            loan._check_repeat_loan_eligibility(
                loan.employee_id, exclude_loan_ids=loan.ids
            )
            workflow = loan._workflow_for_company()
            loan.approval_line_ids.sudo().unlink()
            lines = self.env["hr.loan.approval.line"].sudo().create(
                [
                    {
                        "loan_id": loan.id,
                        "workflow_step_id": step.id,
                        "sequence": step.sequence,
                        "name": step.name,
                        "approver_id": step.approver_id.id,
                        "step_type": step.step_type,
                        "status": "pending",
                    }
                    for step in workflow.step_ids.sorted(
                        lambda step: (step.sequence, step.id)
                    )
                ]
            )
            first_line = lines[0]
            first_line.write({"status": "waiting"})
            loan.with_context(loan_workflow_action=True).write(
                {
                    "workflow_id": workflow.id,
                    "current_approval_line_id": first_line.id,
                    "state": "waiting_approval_1",
                    "rejection_reason": False,
                }
            )
            loan._schedule_current_approval_activity()
        return True

    def _approval_activity_domain(self, user=None):
        self.ensure_one()
        domain = [
            ("res_model_id", "=", self.env["ir.model"]._get_id("hr.loan")),
            ("res_id", "=", self.id),
            (
                "activity_type_id",
                "=",
                self.env.ref("mail.mail_activity_data_todo").id,
            ),
        ]
        if user:
            domain.append(("user_id", "=", user.id))
        return domain

    def _schedule_current_approval_activity(self):
        self.ensure_one()
        line = self.current_approval_line_id
        if not line:
            return
        note = Markup(
            "<p>%s</p><ul><li>%s</li><li>%s</li><li>%s</li></ul>"
        ) % (
            escape("يوجد طلب سلفة بانتظار إجراءك في المرحلة الحالية."),
            escape("رقم الطلب: %s" % self.name),
            escape("الموظف: %s" % self.employee_id.display_name),
            escape("المرحلة: %s" % line.name),
        )
        self.env["mail.activity"].sudo().create(
            {
                "activity_type_id": self.env.ref(
                    "mail.mail_activity_data_todo"
                ).id,
                "summary": "مطلوب إجراء على طلب سلفة",
                "note": note,
                "date_deadline": fields.Date.context_today(self),
                "user_id": line.approver_id.id,
                "res_id": self.id,
                "res_model_id": self.env["ir.model"]._get_id("hr.loan"),
            }
        )
        self.sudo().message_subscribe(
            partner_ids=line.approver_id.partner_id.ids
        )

    def _complete_approval_activity(self, user):
        activities = self.env["mail.activity"].sudo().search(
            self._approval_activity_domain(user)
        )
        if activities:
            activities.action_done()

    def _check_current_approver(self):
        self.ensure_one()
        if (
            self.state != "waiting_approval_1"
            or not self.current_approval_line_id
            or self.current_approver_id != self.env.user
        ):
            raise AccessError(_("This loan is not waiting for your action."))

    def _lock_for_workflow_action(self):
        if not self:
            return
        self.flush_model(["state", "current_approval_line_id"])
        self.env.cr.execute(
            "SELECT id FROM hr_loan WHERE id IN %s FOR UPDATE",
            [tuple(self.ids)],
        )
        self.invalidate_recordset(
            ["state", "current_approval_line_id", "current_approver_id"]
        )

    def _workflow_validate_step(self, approval_line):
        """Extension hook for specialized steps such as accounting."""
        return True

    def _workflow_after_step_approved(self, approval_line):
        """Extension hook called after the current step is approved."""
        return True

    def _loan_finalize_approval(self):
        self.ensure_one()
        self._lock_employee_for_repeat_loan_check()
        self._check_repeat_loan_eligibility(
            self.employee_id, exclude_loan_ids=self.ids
        )
        if not self.loan_lines:
            self.with_context(
                loan_workflow_action=True
            ).action_compute_installment()
        self.with_context(loan_workflow_action=True).write(
            {"state": "approve", "current_approval_line_id": False}
        )

    def action_workflow_approve(self):
        self._lock_for_workflow_action()
        for loan in self:
            loan._check_current_approver()
            line = loan.current_approval_line_id
            is_final_step = not loan.approval_line_ids.filtered(
                lambda candidate: candidate.status == "pending"
            )
            if is_final_step:
                # Check before specialized final-step hooks can create an
                # accounting entry or another irreversible business effect.
                loan._lock_employee_for_repeat_loan_check()
                loan._check_repeat_loan_eligibility(
                    loan.employee_id, exclude_loan_ids=loan.ids
                )
            loan._workflow_validate_step(line)
            line.sudo().write(
                {
                    "status": "approved",
                    "action_by_id": self.env.user.id,
                    "action_date": fields.Datetime.now(),
                }
            )
            loan._workflow_after_step_approved(line)
            loan._complete_approval_activity(self.env.user)
            next_line = loan.approval_line_ids.filtered(
                lambda candidate: candidate.status == "pending"
            ).sorted(lambda candidate: (candidate.sequence, candidate.id))[:1]
            if next_line:
                next_line.sudo().write({"status": "waiting"})
                loan.with_context(loan_workflow_action=True).write(
                    {
                        "current_approval_line_id": next_line.id,
                        "rejection_reason": False,
                    }
                )
                loan._schedule_current_approval_activity()
            else:
                loan._loan_finalize_approval()
        return True

    def action_workflow_reject(self):
        self._lock_for_workflow_action()
        for loan in self:
            loan._check_current_approver()
            if not loan.rejection_reason:
                raise ValidationError(
                    _("Enter a rejection reason before rejecting the loan.")
                )
            line = loan.current_approval_line_id
            line.sudo().write(
                {
                    "status": "rejected",
                    "action_by_id": self.env.user.id,
                    "action_date": fields.Datetime.now(),
                }
            )
            loan.approval_line_ids.filtered(
                lambda item: item.status == "pending"
            ).sudo().write({"status": "cancelled"})
            loan._complete_approval_activity(self.env.user)
            loan.with_context(loan_workflow_action=True).write(
                {"state": "refuse", "current_approval_line_id": False}
            )
        return True

    def action_approve(self):
        return self.action_workflow_approve()

    def action_refuse(self):
        return self.action_workflow_reject()

    def action_cancel(self):
        self._check_owner_or_manager()
        for loan in self:
            if loan.state != "draft":
                raise UserError(_("Only draft loan requests can be cancelled."))
            loan.with_context(loan_workflow_action=True).write({"state": "cancel"})
        return True

    def action_reset_to_draft(self):
        if not self._is_loan_manager():
            raise AccessError(
                _("Only loan administrators can reset a request to draft.")
            )
        for loan in self:
            if loan.state not in (
                "waiting_approval_1",
                "waiting_approval_2",
                "refuse",
                "cancel",
            ):
                raise UserError(
                    _(
                        "Only pending, refused, or cancelled loan requests can "
                        "be reset to draft."
                    )
                )
            self.env["mail.activity"].sudo().search(
                loan._approval_activity_domain()
            ).unlink()
            loan.approval_line_ids.sudo().unlink()
            loan.with_context(loan_workflow_action=True).write(
                {
                    "state": "draft",
                    "workflow_id": False,
                    "current_approval_line_id": False,
                    "rejection_reason": False,
                }
            )
        return True

    def write(self, vals):
        workflow_fields = {
            "state",
            "workflow_id",
            "approval_line_ids",
            "current_approval_line_id",
            "current_approver_id",
            "current_step_name",
            "current_step_type",
        }
        if workflow_fields.intersection(vals) and not self.env.context.get(
            "loan_workflow_action"
        ):
            raise AccessError(
                _("Workflow fields can only be changed through loan actions.")
            )
        if "employee_id" in vals and self._is_loan_manager():
            employee = self.env["hr.employee"].sudo().browse(
                vals["employee_id"]
            ).exists()
            if employee:
                vals["company_id"] = employee.company_id.id
                vals["currency_id"] = employee.company_id.currency_id.id
        if self.env.context.get("loan_workflow_action") or self._is_loan_manager():
            return super().write(vals)

        mail_fields = {
            "message_follower_ids",
            "message_partner_ids",
            "message_main_attachment_id",
            "activity_ids",
        }
        business_fields = set(vals) - mail_fields
        employee_editable_fields = {
            "employee_id",
            "loan_amount",
            "installment",
            "payment_date",
        }
        for loan in self:
            is_owner = loan.employee_id.user_id == self.env.user
            is_current_approver = loan.current_approver_id == self.env.user
            if is_current_approver and loan.state == "waiting_approval_1":
                if business_fields - {"rejection_reason"}:
                    raise AccessError(
                        _(
                            "Approvers can only enter a rejection reason from this screen."
                        )
                    )
            elif is_owner:
                if loan.state != "draft" and business_fields:
                    raise AccessError(
                        _("A submitted loan request cannot be modified.")
                    )
                if business_fields - employee_editable_fields:
                    raise AccessError(
                        _(
                            "Employees can only change the requested amount, "
                            "installment count, and payment start date."
                        )
                    )
                if "employee_id" in vals:
                    employee = self.env["hr.employee"].sudo().browse(
                        vals["employee_id"]
                    )
                    if employee.user_id != self.env.user:
                        raise AccessError(
                            _("You can only request a loan for yourself.")
                        )
            elif business_fields:
                raise AccessError(
                    _("You are not allowed to modify this loan request.")
                )
        return super().write(vals)

    def unlink(self):
        self._check_owner_or_manager()
        if any(loan.state not in ("draft", "cancel") for loan in self):
            raise UserError(
                _("Only draft or cancelled loan requests can be deleted.")
            )
        return super().unlink()


class HrLoanLine(models.Model):
    _name = "hr.loan.line"
    _description = "Installment Line"
    _order = "date, id"
    _rec_name = "loan_id"

    date = fields.Date(
        string="Payment Date", required=True, help="Date of the payment"
    )
    employee_id = fields.Many2one(
        "hr.employee", string="Employee", help="Employee"
    )
    amount = fields.Monetary(string="Amount", required=True, help="Amount")
    currency_id = fields.Many2one(
        related="loan_id.currency_id", store=True, readonly=True
    )
    paid = fields.Boolean(
        string="Paid",
        help="Indicates whether the installment has been paid.",
    )
    loan_id = fields.Many2one(
        "hr.loan",
        string="Loan Ref.",
        required=True,
        ondelete="cascade",
        index=True,
    )
    payslip_id = fields.Many2one(
        "hr.payslip",
        string="Payslip Ref.",
        help="Reference to the associated payslip, if any.",
    )

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HrOvertimeAssignment(models.Model):
    _name = "hr.overtime.assignment"
    _description = "Overtime Work Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_datetime desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False, tracking=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        tracking=True,
        default=lambda self: self._default_employee(),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        tracking=True,
        default=lambda self: self.env.company,
    )
    branch_id = fields.Many2one(
        "res.branch",
        string="Branch",
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self.env.user.branch_id,
    )
    department_id = fields.Many2one("hr.department", string="Department", tracking=True)
    manager_id = fields.Many2one("hr.employee", string="Direct Manager", tracking=True)
    start_datetime = fields.Datetime(required=True, tracking=True)
    end_datetime = fields.Datetime(required=True, tracking=True)
    break_hours = fields.Float(default=0.0, tracking=True)
    total_hours = fields.Float(compute="_compute_total_hours", store=True, tracking=True)
    assignment_reason = fields.Text(required=True, tracking=True)
    work_location = fields.Char()
    compensation_type = fields.Selection(
        [("cash", "Cash Overtime Pay"), ("comp_leave", "Compensatory Paid Leave")],
        required=True,
        default="cash",
        tracking=True,
    )
    compensatory_leave_hours = fields.Float(
        compute="_compute_compensatory_leave_hours", store=True
    )
    employee_consented = fields.Boolean(readonly=True, copy=False, tracking=True)
    consented_by = fields.Many2one("res.users", readonly=True, copy=False)
    consented_at = fields.Datetime(readonly=True, copy=False)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "hr_overtime_assignment_attachment_rel",
        "assignment_id",
        "attachment_id",
        string="Supporting Attachments",
    )
    manager_approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    manager_approved_at = fields.Datetime(readonly=True, copy=False)
    approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    rejection_reason = fields.Text(copy=False, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("manager_approved", "Manager Approved"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
    )

    @api.model
    def _default_employee(self):
        return self.env["hr.employee"].search([("user_id", "=", self.env.user.id)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env["hr.employee"].sudo().browse(vals.get("employee_id"))
            if (
                employee
                and employee.user_id != self.env.user
                and not self.env.user.has_group(
                    "eljohany_employee_forms.group_employee_forms_manager"
                )
            ):
                raise AccessError(_("You can only create assignments for yourself."))
            if employee:
                vals.setdefault("company_id", employee.company_id.id)
                vals.setdefault(
                    "branch_id", (employee.branch_id or employee.user_id.branch_id).id
                )
                vals.setdefault("department_id", employee.department_id.id)
                vals.setdefault("manager_id", employee.parent_id.id)
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("hr.overtime.assignment")
                    or "New"
                )
        return super().create(vals_list)

    @api.depends("start_datetime", "end_datetime", "break_hours")
    def _compute_total_hours(self):
        for record in self:
            hours = 0.0
            if record.start_datetime and record.end_datetime:
                hours = (record.end_datetime - record.start_datetime).total_seconds() / 3600.0
                hours -= record.break_hours
            record.total_hours = max(hours, 0.0)

    @api.depends("total_hours", "compensation_type")
    def _compute_compensatory_leave_hours(self):
        for record in self:
            record.compensatory_leave_hours = (
                record.total_hours * 1.5 if record.compensation_type == "comp_leave" else 0.0
            )

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if not self.employee_id:
            return
        self.company_id = self.employee_id.company_id
        self.department_id = self.employee_id.department_id
        self.manager_id = self.employee_id.parent_id
        self.branch_id = self.employee_id.branch_id or self.employee_id.user_id.branch_id

    @api.constrains("start_datetime", "end_datetime", "break_hours")
    def _check_duration(self):
        for record in self:
            if record.break_hours < 0:
                raise ValidationError(_("Break hours cannot be negative."))
            if record.start_datetime and record.end_datetime:
                if record.end_datetime <= record.start_datetime:
                    raise ValidationError(_("The end time must be after the start time."))
                if record.total_hours <= 0:
                    raise ValidationError(_("The overtime duration must be greater than zero."))

    @api.constrains("employee_id", "branch_id", "company_id")
    def _check_branch_company(self):
        for record in self:
            if record.branch_id.company_id != record.company_id:
                raise ValidationError(_("The branch must belong to the selected company."))
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(
                    _("The employee must belong to the selected company.")
                )

    def _check_owner_or_manager(self):
        if self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            return
        if any(
            record.employee_id.user_id != self.env.user
            for record in self
        ):
            raise AccessError(_("You can only process your own assignments."))

    def _check_manager(self):
        if not self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            raise AccessError(_("Only an Employee Forms Manager can perform this action."))

    def action_submit(self):
        self._check_owner_or_manager()
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft assignments can be submitted."))
            if record.total_hours <= 0:
                raise ValidationError(_("The overtime duration must be greater than zero."))
            record.with_context(employee_forms_workflow=True).write({"state": "submitted"})

    def action_employee_consent(self):
        for record in self:
            if record.compensation_type != "comp_leave":
                raise UserError(_("Employee consent is only required for compensatory leave."))
            if record.state not in ("submitted", "manager_approved"):
                raise UserError(_("Consent can only be recorded after submission."))
            is_employee = record.employee_id.user_id == self.env.user
            if not is_employee and not self.env.user.has_group(
                "eljohany_employee_forms.group_employee_forms_manager"
            ):
                raise AccessError(_("Only the employee or a Forms Manager can record consent."))
            record.with_context(employee_forms_workflow=True).write(
                {
                    "employee_consented": True,
                    "consented_by": self.env.user.id,
                    "consented_at": fields.Datetime.now(),
                }
            )

    def action_manager_approve(self):
        self._check_manager()
        for record in self:
            if record.state != "submitted":
                raise UserError(_("Only submitted assignments can receive manager approval."))
            record.with_context(employee_forms_workflow=True).write(
                {
                    "state": "manager_approved",
                    "manager_approved_by": self.env.user.id,
                    "manager_approved_at": fields.Datetime.now(),
                }
            )

    def action_approve(self):
        self._check_manager()
        for record in self:
            if record.state != "manager_approved":
                raise UserError(_("The direct manager approval is required first."))
            if record.compensation_type == "comp_leave" and not record.employee_consented:
                raise ValidationError(_("The employee must consent to compensatory leave first."))
            record.with_context(employee_forms_workflow=True).write(
                {
                    "state": "approved",
                    "approved_by": self.env.user.id,
                    "approved_at": fields.Datetime.now(),
                }
            )

    def action_reject(self):
        self._check_manager()
        if any(record.state not in ("submitted", "manager_approved") for record in self):
            raise UserError(_("Only submitted or manager-approved assignments can be rejected."))
        if any(not record.rejection_reason for record in self):
            raise ValidationError(_("Enter a rejection reason first."))
        self.with_context(employee_forms_workflow=True).write({"state": "rejected"})

    def action_cancel(self):
        self._check_owner_or_manager()
        if any(record.state not in ("draft", "submitted") for record in self):
            raise UserError(_("Only draft or submitted assignments can be cancelled."))
        self.with_context(employee_forms_workflow=True).write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self._check_manager()
        if any(record.state not in ("rejected", "cancelled") for record in self):
            raise UserError(_("Only rejected or cancelled assignments can return to draft."))
        self.with_context(employee_forms_workflow=True).write(
            {
                "state": "draft",
                "rejection_reason": False,
                "employee_consented": False,
                "consented_by": False,
                "consented_at": False,
                "manager_approved_by": False,
                "manager_approved_at": False,
                "approved_by": False,
                "approved_at": False,
            }
        )

    def write(self, vals):
        workflow_fields = {
            "state",
            "employee_consented",
            "consented_by",
            "consented_at",
            "manager_approved_by",
            "manager_approved_at",
            "approved_by",
            "approved_at",
        }
        if workflow_fields.intersection(vals) and not self.env.context.get(
            "employee_forms_workflow"
        ):
            raise AccessError(
                _("Workflow and audit fields can only be changed through the form actions.")
            )
        if "employee_id" in vals and not self.env.user.has_group(
            "eljohany_employee_forms.group_employee_forms_manager"
        ):
            employee = self.env["hr.employee"].sudo().browse(vals["employee_id"])
            if employee.user_id != self.env.user:
                raise AccessError(_("You can only create assignments for yourself."))
        if not self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            protected = self.filtered(lambda record: record.state != "draft")
            business_fields = set(vals) - {"message_follower_ids", "activity_ids"}
            if (
                protected
                and business_fields
                and not self.env.context.get("employee_forms_workflow")
            ):
                raise AccessError(
                    _("Submitted assignments can only be changed by a Forms Manager.")
                )
        return super().write(vals)

    def unlink(self):
        if any(record.state not in ("draft", "cancelled") for record in self):
            raise UserError(_("Only draft or cancelled assignments can be deleted."))
        self._check_owner_or_manager()
        return super().unlink()

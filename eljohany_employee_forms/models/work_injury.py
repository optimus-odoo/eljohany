from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HrWorkInjuryReport(models.Model):
    _name = "hr.work.injury.report"
    _description = "Work Injury or Occupational Accident Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "accident_datetime desc, id desc"

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
    job_id = fields.Many2one("hr.job", string="Job Position", tracking=True)
    accident_datetime = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)
    accident_location = fields.Char(required=True, tracking=True)
    accident_type = fields.Selection(
        [
            ("workplace", "Workplace Accident"),
            ("commute", "Commuting Accident"),
            ("mission", "Work Mission Accident"),
            ("occupational_disease", "Occupational Disease"),
            ("other", "Other"),
        ],
        required=True,
        default="workplace",
        tracking=True,
    )
    severity = fields.Selection(
        [
            ("minor", "Minor"),
            ("moderate", "Moderate"),
            ("serious", "Serious"),
            ("fatal", "Fatal"),
        ],
        required=True,
        default="minor",
        tracking=True,
    )
    description = fields.Text(required=True, tracking=True)
    injured_body_part = fields.Char()
    witness_names = fields.Text()
    immediate_action = fields.Text(string="First Aid and Immediate Action")
    medical_provider = fields.Char()
    absence_days = fields.Integer(default=0)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "hr_work_injury_attachment_rel",
        "report_id",
        "attachment_id",
        string="Supporting Attachments",
    )
    gosi_reported = fields.Boolean(string="Reported to GOSI", tracking=True)
    gosi_report_number = fields.Char(tracking=True)
    gosi_report_date = fields.Date(tracking=True)
    investigation_result = fields.Text(tracking=True)
    root_cause = fields.Text()
    corrective_actions = fields.Text(tracking=True)
    closed_by = fields.Many2one("res.users", readonly=True, copy=False)
    closed_at = fields.Datetime(readonly=True, copy=False)
    rejection_reason = fields.Text(copy=False, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("investigation", "Under Investigation"),
            ("closed", "Closed"),
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
                raise AccessError(_("You can only create reports for yourself."))
            if employee:
                vals.setdefault("company_id", employee.company_id.id)
                vals.setdefault(
                    "branch_id", (employee.branch_id or employee.user_id.branch_id).id
                )
                vals.setdefault("department_id", employee.department_id.id)
                vals.setdefault("job_id", employee.job_id.id)
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("hr.work.injury.report")
                    or "New"
                )
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if not self.employee_id:
            return
        self.company_id = self.employee_id.company_id
        self.department_id = self.employee_id.department_id
        self.job_id = self.employee_id.job_id
        self.branch_id = self.employee_id.branch_id or self.employee_id.user_id.branch_id

    @api.constrains("employee_id", "branch_id", "company_id")
    def _check_branch_company(self):
        for record in self:
            if record.branch_id.company_id != record.company_id:
                raise ValidationError(_("The branch must belong to the selected company."))
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(
                    _("The employee must belong to the selected company.")
                )

    @api.constrains("absence_days")
    def _check_absence_days(self):
        if any(record.absence_days < 0 for record in self):
            raise ValidationError(_("Absence days cannot be negative."))

    def _check_owner_or_manager(self):
        if self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            return
        if any(
            record.employee_id.user_id != self.env.user
            for record in self
        ):
            raise AccessError(_("You can only process your own reports."))

    def action_submit(self):
        self._check_owner_or_manager()
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft reports can be submitted."))
            record.with_context(employee_forms_workflow=True).write({"state": "submitted"})

    def action_start_investigation(self):
        self._check_manager()
        for record in self:
            if record.state != "submitted":
                raise UserError(_("Only submitted reports can enter investigation."))
            record.with_context(employee_forms_workflow=True).write({"state": "investigation"})

    def action_close(self):
        self._check_manager()
        for record in self:
            if record.state != "investigation":
                raise UserError(_("Only reports under investigation can be closed."))
            if not record.investigation_result or not record.corrective_actions:
                raise ValidationError(
                    _("Enter the investigation result and corrective actions before closing.")
                )
            record.with_context(employee_forms_workflow=True).write(
                {
                    "state": "closed",
                    "closed_by": self.env.user.id,
                    "closed_at": fields.Datetime.now(),
                }
            )

    def action_reject(self):
        self._check_manager()
        if any(record.state not in ("submitted", "investigation") for record in self):
            raise UserError(
                _("Only submitted reports or reports under investigation can be rejected.")
            )
        if any(not record.rejection_reason for record in self):
            raise ValidationError(_("Enter a rejection reason first."))
        self.with_context(employee_forms_workflow=True).write({"state": "rejected"})

    def action_cancel(self):
        self._check_owner_or_manager()
        if any(record.state not in ("draft", "submitted") for record in self):
            raise UserError(_("Only draft or submitted reports can be cancelled."))
        self.with_context(employee_forms_workflow=True).write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self._check_manager()
        if any(record.state not in ("rejected", "cancelled") for record in self):
            raise UserError(_("Only rejected or cancelled reports can return to draft."))
        self.with_context(employee_forms_workflow=True).write(
            {"state": "draft", "rejection_reason": False}
        )

    def _check_manager(self):
        if not self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            raise AccessError(_("Only an Employee Forms Manager can perform this action."))

    def write(self, vals):
        workflow_fields = {"state", "closed_by", "closed_at"}
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
                raise AccessError(_("You can only create reports for yourself."))
        if not self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            protected = self.filtered(lambda record: record.state != "draft")
            business_fields = set(vals) - {"message_follower_ids", "activity_ids"}
            if (
                protected
                and business_fields
                and not self.env.context.get("employee_forms_workflow")
            ):
                raise AccessError(_("Submitted reports can only be changed by a Forms Manager."))
        return super().write(vals)

    def unlink(self):
        if any(record.state not in ("draft", "cancelled") for record in self):
            raise UserError(_("Only draft or cancelled reports can be deleted."))
        self._check_owner_or_manager()
        return super().unlink()

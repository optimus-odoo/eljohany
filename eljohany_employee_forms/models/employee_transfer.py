import logging

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_logger = logging.getLogger(__name__)


class HrEmployeeTransfer(models.Model):
    _name = "hr.employee.transfer"
    _description = "Employee Branch Transfer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "effective_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False, tracking=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        tracking=True,
        default=lambda self: self._default_employee(),
    )
    effective_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    reason = fields.Text(required=True, tracking=True)
    handover_notes = fields.Text()
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "hr_employee_transfer_attachment_rel",
        "transfer_id",
        "attachment_id",
        string="Supporting Attachments",
    )

    from_company_id = fields.Many2one(
        "res.company", string="From Company", readonly=True, tracking=True
    )
    from_branch_id = fields.Many2one(
        "res.branch", string="From Branch", readonly=True, tracking=True
    )
    from_department_id = fields.Many2one(
        "hr.department", string="From Department", readonly=True
    )
    from_job_id = fields.Many2one("hr.job", string="From Job", readonly=True)
    from_manager_id = fields.Many2one(
        "hr.employee", string="From Manager", readonly=True
    )
    from_work_location_id = fields.Many2one(
        "hr.work.location", string="From Work Location", readonly=True
    )

    to_company_id = fields.Many2one(
        "res.company", string="To Company", required=True, tracking=True
    )
    to_branch_id = fields.Many2one(
        "res.branch",
        string="To Branch",
        required=True,
        tracking=True,
        domain="[('company_id', '=', to_company_id)]",
    )
    to_department_id = fields.Many2one(
        "hr.department",
        string="To Department",
        tracking=True,
        domain="[('company_id', 'in', [False, to_company_id])]",
    )
    to_job_id = fields.Many2one(
        "hr.job",
        string="To Job",
        tracking=True,
        domain="[('company_id', 'in', [False, to_company_id])]",
    )
    to_manager_id = fields.Many2one(
        "hr.employee",
        string="To Manager",
        tracking=True,
        domain="[('company_id', '=', to_company_id)]",
    )
    to_work_location_id = fields.Many2one(
        "hr.work.location",
        string="To Work Location",
        tracking=True,
        domain="[('company_id', '=', to_company_id)]",
    )
    employee_user_id = fields.Many2one(
        "res.users", related="employee_id.user_id", string="Linked User", readonly=True
    )
    approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    applied_by = fields.Many2one("res.users", readonly=True, copy=False)
    applied_at = fields.Datetime(readonly=True, copy=False)
    application_error = fields.Text(readonly=True, copy=False)
    application_failed_at = fields.Datetime(readonly=True, copy=False)
    rejection_reason = fields.Text(copy=False, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved - Awaiting Effective Date"),
            ("applied", "Approved and Applied"),
            ("application_failed", "Application Failed"),
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
        employee_model = self.env["hr.employee"].sudo()
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("hr.employee.transfer") or "New"
            employee = employee_model.browse(vals.get("employee_id"))
            if employee:
                if (
                    employee.user_id != self.env.user
                    and not self.env.user.has_group(
                        "eljohany_employee_forms.group_employee_forms_manager"
                    )
                ):
                    raise AccessError(_("You can only create transfer requests for yourself."))
                vals.update(self._source_values(employee))
        return super().create(vals_list)

    @api.model
    def _source_values(self, employee):
        return {
            "from_company_id": employee.company_id.id,
            "from_branch_id": (employee.branch_id or employee.user_id.branch_id).id,
            "from_department_id": employee.department_id.id,
            "from_job_id": employee.job_id.id,
            "from_manager_id": employee.parent_id.id,
            "from_work_location_id": employee.work_location_id.id,
        }

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if not self.employee_id:
            return
        for field_name, value in self._source_values(self.employee_id).items():
            self[field_name] = value
        self.to_company_id = self.employee_id.company_id
        self.to_branch_id = False
        self.to_department_id = self.employee_id.department_id
        self.to_job_id = self.employee_id.job_id
        self.to_manager_id = self.employee_id.parent_id
        self.to_work_location_id = self.employee_id.work_location_id

    @api.onchange("to_company_id")
    def _onchange_to_company_id(self):
        if self.to_branch_id.company_id != self.to_company_id:
            self.to_branch_id = False
        for field_name in (
            "to_department_id",
            "to_job_id",
            "to_manager_id",
            "to_work_location_id",
        ):
            value = self[field_name]
            if value and value.company_id and value.company_id != self.to_company_id:
                self[field_name] = False

    @api.constrains("to_company_id", "to_branch_id")
    def _check_destination_branch(self):
        for record in self:
            if record.to_branch_id.company_id != record.to_company_id:
                raise ValidationError(
                    _("The destination branch must belong to the destination company.")
                )
            if (
                record.from_company_id == record.to_company_id
                and record.from_branch_id == record.to_branch_id
            ):
                raise ValidationError(
                    _("The destination must differ from the current company or branch.")
                )

    @api.constrains(
        "to_company_id",
        "to_department_id",
        "to_job_id",
        "to_manager_id",
        "to_work_location_id",
    )
    def _check_destination_relations(self):
        for record in self:
            for value in (
                record.to_department_id,
                record.to_job_id,
                record.to_manager_id,
                record.to_work_location_id,
            ):
                if value and value.company_id and value.company_id != record.to_company_id:
                    raise ValidationError(
                        _(
                            "All destination organizational data must belong to the "
                            "destination company."
                        )
                    )

    def _check_owner_or_manager(self):
        if self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            return
        if any(
            record.employee_id.user_id != self.env.user
            for record in self
        ):
            raise AccessError(_("You can only process your own transfer requests."))

    def _check_manager(self):
        if not self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            raise AccessError(_("Only an Employee Forms Manager can perform this action."))

    def action_submit(self):
        self._check_owner_or_manager()
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft transfer requests can be submitted."))
            record.with_context(employee_forms_workflow=True).write({"state": "submitted"})

    def action_approve_and_apply(self):
        self._check_manager()
        for record in self:
            if record.state != "submitted":
                raise UserError(_("Only submitted transfer requests can be approved and applied."))
            record._validate_source_unchanged()
            if record.effective_date > fields.Date.context_today(record):
                record.with_context(employee_forms_workflow=True).write(
                    {"state": "approved", "approved_by": self.env.user.id}
                )
            else:
                record._apply_transfer()

    def _validate_source_unchanged(self):
        self.ensure_one()
        employee = self.employee_id.sudo()
        current_branch = employee.branch_id or employee.user_id.branch_id
        if (
            employee.company_id != self.from_company_id
            or current_branch != self.from_branch_id
        ):
            raise ValidationError(
                _(
                    "The employee's current company or branch changed after this request "
                    "was created. Reset the request to draft and review it again."
                )
            )

    def _apply_transfer(self):
        self.ensure_one()
        self._validate_source_unchanged()
        employee = self.employee_id.sudo()
        user = employee.user_id.sudo()

        employee_values = {
            "company_id": self.to_company_id.id,
            "branch_id": self.to_branch_id.id,
            "department_id": self.to_department_id.id,
            "job_id": self.to_job_id.id,
            "parent_id": self.to_manager_id.id,
            "work_location_id": self.to_work_location_id.id,
        }
        # Keep the attendance integration's actual branch aligned when that optional
        # module is installed. Its own validations (for example, an open attendance)
        # remain authoritative and will safely abort the whole transaction.
        if "api_branch_id" in employee._fields:
            employee_values["api_branch_id"] = self.to_branch_id.id
        employee.with_company(self.to_company_id).write(employee_values)

        if user:
            # Add allowed values first so the branch module's constraints accept
            # changing the user's active company and branch in the second write.
            user.write(
                {
                    "company_ids": [(4, self.to_company_id.id)],
                    "branch_ids": [(4, self.to_branch_id.id)],
                }
            )
            user.with_company(self.to_company_id).write(
                {"company_id": self.to_company_id.id, "branch_id": self.to_branch_id.id}
            )

        self.with_context(employee_forms_workflow=True).write(
            {
                "state": "applied",
                "approved_by": self.approved_by.id or self.env.user.id,
                "applied_by": self.env.user.id,
                "applied_at": fields.Datetime.now(),
            }
        )
        self.message_post(
            body=Markup("<p>%s</p><ul><li>%s</li><li>%s</li></ul>")
            % (
                escape(
                    _(
                        "The employee transfer was approved and applied to the actual "
                        "records."
                    )
                ),
                escape(
                    _(
                        "Company: %(old)s → %(new)s",
                        old=self.from_company_id.display_name,
                        new=self.to_company_id.display_name,
                    )
                ),
                escape(
                    _(
                        "Branch: %(old)s → %(new)s",
                        old=self.from_branch_id.display_name or "-",
                        new=self.to_branch_id.display_name,
                    )
                ),
            )
        )

    @api.model
    def _cron_apply_due_transfers(self):
        due_transfers = self.sudo().search(
            [
                ("state", "=", "approved"),
                ("effective_date", "<=", fields.Date.context_today(self)),
            ]
        )
        for transfer in due_transfers:
            try:
                with self.env.cr.savepoint():
                    transfer._apply_transfer()
            except Exception as error:
                _logger.exception(
                    "Could not apply scheduled employee transfer %s", transfer.display_name
                )
                transfer.with_context(employee_forms_workflow=True).write(
                    {
                        "state": "application_failed",
                        "application_error": str(error),
                        "application_failed_at": fields.Datetime.now(),
                    }
                )

    def action_reject(self):
        self._check_manager()
        if any(record.state != "submitted" for record in self):
            raise UserError(_("Only submitted transfer requests can be rejected."))
        if any(not record.rejection_reason for record in self):
            raise ValidationError(_("Enter a rejection reason first."))
        self.with_context(employee_forms_workflow=True).write({"state": "rejected"})

    def action_cancel(self):
        self._check_owner_or_manager()
        if any(record.state == "approved" for record in self):
            self._check_manager()
        if any(record.state not in ("draft", "submitted", "approved") for record in self):
            raise UserError(
                _("Only draft, submitted, or scheduled transfer requests can be cancelled.")
            )
        self.with_context(employee_forms_workflow=True).write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self._check_manager()
        for record in self:
            if record.state not in (
                "rejected",
                "cancelled",
                "approved",
                "application_failed",
            ):
                raise UserError(
                    _(
                        "Only rejected, cancelled, scheduled, or failed transfers can "
                        "return to draft."
                    )
                )
            values = {
                "state": "draft",
                "rejection_reason": False,
                "approved_by": False,
                "application_error": False,
                "application_failed_at": False,
            }
            values.update(self._source_values(record.employee_id.sudo()))
            record.with_context(employee_forms_workflow=True).write(values)

    def write(self, vals):
        workflow_fields = {
            "state",
            "approved_by",
            "applied_by",
            "applied_at",
            "application_error",
            "application_failed_at",
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
                raise AccessError(_("You can only create transfer requests for yourself."))
        if "employee_id" in vals:
            employee = self.env["hr.employee"].sudo().browse(vals["employee_id"])
            vals.update(self._source_values(employee))
        mail_fields = {
            "message_follower_ids",
            "activity_ids",
            "message_partner_ids",
            "message_main_attachment_id",
        }
        if not self.env.user.has_group("eljohany_employee_forms.group_employee_forms_manager"):
            protected = self.filtered(lambda record: record.state != "draft")
            business_fields = set(vals) - mail_fields
            if (
                protected
                and business_fields
                and not self.env.context.get("employee_forms_workflow")
            ):
                raise AccessError(_("Submitted transfers can only be changed by a Forms Manager."))
        business_fields = set(vals) - mail_fields
        if (
            business_fields
            and any(record.state == "applied" for record in self)
            and not self.env.context.get("employee_forms_workflow")
        ):
            raise AccessError(_("An applied transfer record cannot be changed."))
        return super().write(vals)

    def unlink(self):
        if any(record.state not in ("draft", "cancelled") for record in self):
            raise UserError(_("Only draft or cancelled transfer requests can be deleted."))
        self._check_owner_or_manager()
        return super().unlink()

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    api_branch_id = fields.Many2one(
        "res.branch",
        string="Attendance API Branch",
        index=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    api_employee_number = fields.Char(string="API Employee Number", index=True, copy=False)
    api_external_id = fields.Char(string="External HR Employee ID", index=True, copy=False)
    api_hire_date = fields.Date(string="API Hire Date")
    api_access_enabled = fields.Boolean(string="Attendance API Access", default=False)
    api_credential_ids = fields.One2many(
        "hr.attendance.api.credential", "employee_id", string="API Credentials"
    )

    _sql_constraints = [
        (
            "api_employee_number_company_unique",
            "unique(company_id, api_employee_number)",
            "The API employee number must be unique per company.",
        ),
        (
            "api_external_employee_company_unique",
            "unique(company_id, api_external_id)",
            "The external HR employee ID must be unique per company.",
        ),
    ]

    def write(self, vals):
        deactivating = (
            ("active" in vals and not vals["active"])
            or ("api_access_enabled" in vals and not vals["api_access_enabled"])
        )
        branch_changing = "api_branch_id" in vals and any(
            employee.api_branch_id.id != vals["api_branch_id"] for employee in self
        )
        if (deactivating or branch_changing) and self.env["hr.attendance"].sudo().search_count(
            [("employee_id", "in", self.ids), ("check_out", "=", False)]
        ):
            raise ValidationError(
                _("Attendance API access or branch cannot change while the employee is checked in.")
            )
        result = super().write(vals)
        if deactivating or branch_changing:
            tokens = self.env["hr.attendance.api.token"].sudo().search(
                [("employee_id", "in", self.ids), ("revoked_at", "=", False)]
            )
            if tokens:
                tokens.write({"revoked_at": fields.Datetime.now()})
        return result

    @api.constrains("api_branch_id", "company_id")
    def _check_api_branch_company(self):
        for employee in self:
            if (
                employee.api_branch_id
                and employee.api_branch_id.company_id != employee.company_id
            ):
                raise ValidationError(_("The employee and attendance branch must belong to the same company."))

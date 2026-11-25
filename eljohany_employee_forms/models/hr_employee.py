from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    branch_id = fields.Many2one(
        "res.branch",
        string="Branch",
        domain="[('company_id', '=', company_id)]",
        groups=(
            "hr.group_hr_user,base.group_system,"
            "eljohany_employee_forms.group_employee_forms_user"
        ),
        tracking=True,
    )

    @api.constrains("branch_id", "company_id")
    def _check_employee_branch_company(self):
        for employee in self:
            if employee.branch_id and employee.branch_id.company_id != employee.company_id:
                raise ValidationError(
                    _("The employee branch must belong to the employee company.")
                )

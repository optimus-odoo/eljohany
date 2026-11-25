from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ExecutiveIntelligenceDashboard(models.Model):
    _name = "executive.intelligence.dashboard"
    _description = "Executive Intelligence Dashboard"
    _order = "sequence, id"

    name = fields.Char(string="Dashboard Name", required=True, translate=True)
    code = fields.Char(string="Dashboard Code", required=True, index=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(default=True)
    icon = fields.Char(string="Icon", default="fa-chart-line")
    required_module_names = fields.Char(
        string="Required Modules",
        help="Comma-separated technical module names. All must be installed."
    )
    sensitivity = fields.Selection(
        [
            ("normal", "Normal"),
            ("financial", "Financial"),
            ("hr", "Human Resources"),
            ("payroll", "Payroll"),
        ],
        required=True,
        default="normal",
        string="Sensitivity",
    )

    _sql_constraints = [
        ("dashboard_code_uniq", "unique(code)", "Dashboard code must be unique."),
    ]

    @api.constrains("code")
    def _check_code(self):
        for record in self:
            if not record.code or not record.code.replace("_", "").isalnum():
                raise ValidationError(
                    _(
                        "Dashboard code may contain only letters, numbers, "
                        "and underscores."
                    )
                )

    def _required_module_list(self):
        self.ensure_one()
        return [
            item.strip()
            for item in (self.required_module_names or "").split(",")
            if item.strip()
        ]

    def is_available(self):
        """Return availability using module metadata only, never business data."""
        self.ensure_one()
        required = self._required_module_list()
        if not required:
            return True
        installed = self.env["ir.module.module"].sudo().search_count(
            [("name", "in", required), ("state", "=", "installed")]
        )
        return installed == len(required)

    @api.model
    def _ei_sync_provider_availability(self):
        """Archive catalog placeholders that have no installed data provider."""
        supported_codes = self.env[
            "executive.intelligence.service"
        ]._ei_supported_dashboard_codes()
        dashboards = self.sudo().with_context(active_test=False).search([])
        to_activate = dashboards.filtered(
            lambda dashboard: dashboard.code in supported_codes
            and not dashboard.active
        )
        to_archive = dashboards.filtered(
            lambda dashboard: dashboard.code not in supported_codes
            and dashboard.active
        )
        if to_activate:
            to_activate.write({"active": True})
        if to_archive:
            to_archive.write({"active": False})
        return True


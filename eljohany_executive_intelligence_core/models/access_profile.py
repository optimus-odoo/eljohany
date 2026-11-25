from odoo import fields, models


class ExecutiveIntelligenceAccessProfile(models.Model):
    _name = "executive.intelligence.access.profile"
    _description = "Executive Intelligence Access Profile"
    _order = "name, id"

    name = fields.Char(string="Profile Name", required=True, translate=True)
    auto_code = fields.Char(
        readonly=True,
        copy=False,
        index=True,
        help="Technical key used to update automatically generated profiles safely.",
    )
    active = fields.Boolean(default=True)
    dashboard_ids = fields.Many2many(
        "executive.intelligence.dashboard",
        "ei_profile_dashboard_rel",
        "profile_id",
        "dashboard_id",
        string="Allowed Dashboards",
    )
    company_ids = fields.Many2many(
        "res.company",
        "ei_profile_company_rel",
        "profile_id",
        "company_id",
        string="Analytics Companies",
    )
    financial_access = fields.Selection(
        [("none", "None"), ("summary", "Summary"), ("detail", "Details")],
        required=True,
        default="none",
        string="Financial Data Level",
    )
    hr_access = fields.Selection(
        [
            ("none", "None"),
            ("statistics", "Statistics Only"),
            ("employee", "Employee Details"),
            ("payroll", "Payroll and Cost"),
        ],
        required=True,
        default="none",
        string="HR Data Level",
    )
    can_drilldown = fields.Boolean(string="Allow Drill-Down", default=False)
    can_export = fields.Boolean(string="Allow Export", default=False)
    can_forecast = fields.Boolean(string="Allow Forecasts", default=False)
    can_manage_alerts = fields.Boolean(string="Manage Alerts", default=False)
    can_manage_kpis = fields.Boolean(string="Manage KPI Definitions", default=False)

    _sql_constraints = [
        (
            "access_profile_auto_code_uniq",
            "unique(auto_code)",
            "Automatic access profile code must be unique.",
        ),
    ]


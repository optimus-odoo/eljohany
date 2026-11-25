import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    ei_enabled = fields.Boolean(
        string="Executive Intelligence Access",
        compute="_compute_ei_enabled",
        inverse="_inverse_ei_enabled",
    )
    ei_access_profile_id = fields.Many2one(
        "executive.intelligence.access.profile",
        string="Intelligence Access Profile",
        ondelete="restrict",
    )
    ei_custom_access = fields.Boolean(
        string="Use Custom Intelligence Access",
        help="When enabled, the values on this user override the selected profile.",
    )
    ei_dashboard_ids = fields.Many2many(
        "executive.intelligence.dashboard",
        "ei_user_dashboard_rel",
        "user_id",
        "dashboard_id",
        string="Allowed Dashboards",
    )
    ei_company_ids = fields.Many2many(
        "res.company",
        "ei_user_company_rel",
        "user_id",
        "company_id",
        string="Analytics Companies",
        help="Must be a subset of the user's standard allowed companies.",
    )
    ei_financial_access = fields.Selection(
        [("none", "None"), ("summary", "Summary"), ("detail", "Details")],
        required=True,
        default="none",
        string="Financial Data Level",
    )
    ei_hr_access = fields.Selection(
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
    ei_can_drilldown = fields.Boolean(string="Allow Drill-Down")
    ei_can_export = fields.Boolean(string="Allow Export")
    ei_can_forecast = fields.Boolean(string="Allow Forecasts")
    ei_can_manage_alerts = fields.Boolean(string="Manage Alerts")
    ei_can_manage_kpis = fields.Boolean(string="Manage KPI Definitions")
    ei_auto_configured = fields.Boolean(
        string="Automatic Role-Based Configuration",
        copy=False,
        help="The intelligence scope is maintained from the user's standard Odoo roles.",
    )

    @api.model
    def _ei_setup_core_defaults(self):
        """Give the system administrator a complete, safe starting scope.

        Provider modules add only the dashboards they actually implement. The
        method is idempotent and is executed on install and upgrade.
        """
        self.env[
            "executive.intelligence.dashboard"
        ]._ei_sync_provider_availability()
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        admin_group = self.env.ref(
            "eljohany_executive_intelligence_core.group_ei_admin"
        )
        if not administrator:
            return True
        administrator.sudo().with_context(
            _ei_skip_role_sync=True,
            _ei_auto_configuration_write=True,
        ).write(
            {
                "groups_id": [(4, admin_group.id)],
                "ei_access_profile_id": False,
                "ei_custom_access": True,
                "ei_auto_configured": True,
                "ei_company_ids": [(6, 0, administrator.company_ids.ids)],
                "ei_financial_access": "detail",
                "ei_hr_access": "payroll",
                "ei_can_drilldown": True,
                "ei_can_export": True,
                "ei_can_forecast": True,
                "ei_can_manage_alerts": True,
                "ei_can_manage_kpis": True,
            }
        )
        return True

    @api.model
    def _ei_setup_all_defaults(self):
        """Re-run every installed provider's idempotent configuration."""
        self._ei_setup_core_defaults()
        inventory_setup = getattr(self, "_ei_setup_inventory_defaults", None)
        if inventory_setup:
            inventory_setup()
        extended_setup = getattr(self, "_ei_setup_extended_defaults", None)
        if extended_setup:
            extended_setup()
        purchase_setup = getattr(self, "_ei_setup_purchase_defaults", None)
        if purchase_setup:
            purchase_setup()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users:
            snapshot = user._ei_audit_snapshot()
            if snapshot["enabled"] or snapshot["profile_id"] or snapshot["custom"]:
                self.env["executive.intelligence.access.log"].sudo().with_context(
                    _ei_access_log_internal_create=True
                ).create(
                    {
                        "target_user_id": user.id,
                        "changed_by_id": self.env.user.id,
                        "operation": "create",
                        "new_configuration": json.dumps(
                            snapshot, ensure_ascii=False, sort_keys=True
                        ),
                    }
                )
        users._ei_sync_role_based_access()
        return users

    def write(self, vals):
        manual_scope_fields = {
            "ei_enabled",
            "ei_access_profile_id",
            "ei_custom_access",
            "ei_dashboard_ids",
            "ei_company_ids",
            "ei_warehouse_ids",
            "ei_financial_access",
            "ei_hr_access",
            "ei_can_drilldown",
            "ei_can_export",
            "ei_can_forecast",
            "ei_can_manage_alerts",
            "ei_can_manage_kpis",
        }
        if (
            not self.env.context.get("_ei_auto_configuration_write")
            and manual_scope_fields & set(vals)
            and "ei_auto_configured" not in vals
        ):
            vals = {**vals, "ei_auto_configured": False}
        should_audit = not self.env.context.get("_ei_skip_access_audit") and (
            "groups_id" in vals
            or any(field_name.startswith("ei_") for field_name in vals)
        )
        before = {}
        if should_audit:
            before = {user.id: user._ei_audit_snapshot() for user in self}
        sync_roles = (
            not self.env.context.get("_ei_skip_role_sync")
            and bool(
                {
                    "groups_id",
                    "company_id",
                    "company_ids",
                    "allowed_warehouse_ids",
                    "restrict_location",
                }
                & set(vals)
            )
        )
        result = super().write(vals)
        if should_audit:
            for user in self:
                previous = before[user.id]
                current = user._ei_audit_snapshot()
                if current != previous:
                    self.env["executive.intelligence.access.log"].sudo().with_context(
                        _ei_access_log_internal_create=True
                    ).create(
                        {
                            "target_user_id": user.id,
                            "changed_by_id": self.env.user.id,
                            "operation": "write",
                            "previous_configuration": json.dumps(
                                previous, ensure_ascii=False, sort_keys=True
                            ),
                            "new_configuration": json.dumps(
                                current, ensure_ascii=False, sort_keys=True
                            ),
                        }
                    )
        if sync_roles:
            self._ei_sync_role_based_access()
        return result

    @api.depends("groups_id")
    def _compute_ei_enabled(self):
        access_group = self.env.ref(
            "eljohany_executive_intelligence_core.group_ei_user",
            raise_if_not_found=False,
        )
        for user in self:
            user.ei_enabled = bool(access_group and access_group in user.groups_id)

    def _inverse_ei_enabled(self):
        access_group = self.env.ref(
            "eljohany_executive_intelligence_core.group_ei_user"
        )
        for user in self:
            if user.ei_enabled:
                user.with_context(_ei_skip_access_audit=True).groups_id = [
                    (4, access_group.id)
                ]
            else:
                user.with_context(_ei_skip_access_audit=True).groups_id = [
                    (3, access_group.id)
                ]

    @api.constrains("ei_company_ids", "company_ids")
    def _check_ei_companies(self):
        for user in self:
            unauthorized = user.ei_company_ids - user.company_ids
            if unauthorized:
                raise ValidationError(
                    _(
                        "Analytics companies must be included in the user's "
                        "allowed companies."
                    )
                )

    def _ei_effective_access(self):
        """Return a serializable, default-deny access configuration.

        Reading these administration fields with sudo is intentional. It never reads
        business data and prevents access rules on configuration models from making
        runtime authorization inconsistent.
        """
        self.ensure_one()
        user = self.sudo()
        user_company_ids = set(user.company_ids.ids)
        profile = (
            user.ei_access_profile_id
            if not user.ei_custom_access and user.ei_access_profile_id
            else False
        )
        if profile:
            dashboard_ids = profile.dashboard_ids.ids
            configured_company_ids = set(profile.company_ids.ids)
            financial_access = profile.financial_access
            hr_access = profile.hr_access
            can_drilldown = profile.can_drilldown
            can_export = profile.can_export
            can_forecast = profile.can_forecast
            can_manage_alerts = profile.can_manage_alerts
            can_manage_kpis = profile.can_manage_kpis
        else:
            dashboard_ids = user.ei_dashboard_ids.ids if user.ei_custom_access else []
            configured_company_ids = (
                set(user.ei_company_ids.ids) if user.ei_custom_access else set()
            )
            financial_access = user.ei_financial_access
            hr_access = user.ei_hr_access
            can_drilldown = user.ei_can_drilldown
            can_export = user.ei_can_export
            can_forecast = user.ei_can_forecast
            can_manage_alerts = user.ei_can_manage_alerts
            can_manage_kpis = user.ei_can_manage_kpis
        effective_company_ids = sorted(user_company_ids & configured_company_ids)
        return {
            "dashboard_ids": dashboard_ids,
            "company_ids": effective_company_ids,
            "financial_access": financial_access,
            "hr_access": hr_access,
            "can_drilldown": can_drilldown,
            "can_export": can_export,
            "can_forecast": can_forecast,
            "can_manage_alerts": can_manage_alerts,
            "can_manage_kpis": can_manage_kpis,
        }

    def _ei_audit_snapshot(self):
        self.ensure_one()
        access = self._ei_effective_access()
        return {
            "enabled": self.ei_enabled,
            "profile_id": self.ei_access_profile_id.id or False,
            "custom": self.ei_custom_access,
            "auto_configured": self.ei_auto_configured,
            **access,
        }

    def _ei_automatic_dashboard_ids(self):
        self.ensure_one()
        return self.env["executive.intelligence.dashboard"]

    def _ei_automatic_manager_access(self):
        self.ensure_one()
        return self == self.env.ref("base.user_admin", raise_if_not_found=False)

    def _ei_sync_role_based_access(self):
        """Maintain default scopes without overwriting manual configuration."""
        center_group = self.env.ref(
            "eljohany_executive_intelligence_core.group_ei_user",
            raise_if_not_found=False,
        )
        if not center_group:
            return True
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        restriction_group = self.env.ref(
            "user_warehouse_restriction.user_warehouse_restriction_group_user",
            raise_if_not_found=False,
        )
        for user in self.sudo().with_context(active_test=False):
            is_administrator = bool(administrator and user == administrator)
            is_unconfigured = not user.ei_access_profile_id and not user.ei_custom_access
            if not (is_administrator or user.ei_auto_configured or is_unconfigured):
                continue
            dashboards = user._ei_automatic_dashboard_ids()
            if not dashboards and not is_administrator:
                if user.ei_auto_configured:
                    values = {
                        "groups_id": [(3, center_group.id)],
                        "ei_dashboard_ids": [(5, 0, 0)],
                        "ei_company_ids": [(5, 0, 0)],
                        "ei_auto_configured": False,
                    }
                    if "ei_warehouse_ids" in user._fields:
                        values["ei_warehouse_ids"] = [(5, 0, 0)]
                    user.with_context(
                        _ei_skip_role_sync=True,
                        _ei_auto_configuration_write=True,
                    ).write(values)
                continue

            values = {
                "groups_id": [(4, center_group.id)],
                "ei_access_profile_id": False,
                "ei_custom_access": True,
                "ei_auto_configured": True,
                "ei_dashboard_ids": [(6, 0, dashboards.ids)],
                "ei_company_ids": [(6, 0, user.company_ids.ids)],
                "ei_can_drilldown": user._ei_automatic_manager_access(),
                "ei_can_export": user._ei_automatic_manager_access(),
            }
            if "ei_warehouse_ids" in user._fields:
                automatic_scope = getattr(
                    user, "_ei_automatic_warehouse_scope", None
                )
                if automatic_scope:
                    warehouses = automatic_scope(user.company_ids.ids)
                else:
                    warehouses = self.env["stock.warehouse"].sudo().search(
                        [("company_id", "in", user.company_ids.ids)]
                    )
                    if (
                        restriction_group
                        and restriction_group in user.groups_id
                        and "allowed_warehouse_ids" in user._fields
                    ):
                        warehouses &= user.allowed_warehouse_ids
                values["ei_warehouse_ids"] = [(6, 0, warehouses.ids)]
            user.with_context(
                _ei_skip_role_sync=True,
                _ei_auto_configuration_write=True,
            ).write(values)
        return True


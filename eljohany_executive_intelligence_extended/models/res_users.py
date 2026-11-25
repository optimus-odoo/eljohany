from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _ei_group(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _ei_has_any_group(self, xmlids):
        self.ensure_one()
        return any(
            group and group in self.groups_id
            for group in (self._ei_group(xmlid) for xmlid in xmlids)
        )

    def _ei_dashboard(self, code):
        return self.env.ref(
            f"eljohany_executive_intelligence_core.dashboard_{code}"
        )

    def _ei_automatic_dashboard_ids(self):
        self.ensure_one()
        dashboards = super()._ei_automatic_dashboard_ids()
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        is_administrator = bool(administrator and self == administrator)

        if is_administrator:
            for code in (
                "executive",
                "finance",
                "sales",
                "product",
                "forecast",
                "hr",
                "operations",
                "risk",
            ):
                dashboards |= self._ei_dashboard(code)
            return dashboards

        if self._ei_has_any_group(
            (
                "account.group_account_readonly",
                "account.group_account_user",
                "account.group_account_manager",
            )
        ):
            dashboards |= self._ei_dashboard("finance")
        if self._ei_has_any_group(("sales_team.group_sale_salesman",)):
            dashboards |= self._ei_dashboard("sales")
        if self._ei_has_any_group(("stock.group_stock_user",)):
            dashboards |= self._ei_dashboard("product")
        if self._ei_has_any_group(("hr.group_hr_user",)):
            dashboards |= self._ei_dashboard("hr")
        if self._ei_has_any_group(("mrp.group_mrp_user",)):
            dashboards |= self._ei_dashboard("operations")
        if self._ei_has_any_group(("stock.group_stock_manager",)):
            dashboards |= self._ei_dashboard("forecast")
        if self._ei_has_any_group(
            (
                "account.group_account_manager",
                "sales_team.group_sale_manager",
                "stock.group_stock_manager",
                "purchase.group_purchase_manager",
                "hr.group_hr_manager",
                "mrp.group_mrp_manager",
            )
        ):
            dashboards |= self._ei_dashboard("risk")
        return dashboards

    def _ei_automatic_manager_access(self):
        return super()._ei_automatic_manager_access() or self._ei_has_any_group(
            (
                "account.group_account_manager",
                "sales_team.group_sale_manager",
                "hr.group_hr_manager",
                "mrp.group_mrp_manager",
            )
        )

    def _ei_sync_role_based_access(self):
        result = super()._ei_sync_role_based_access()
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        for user in self.sudo().with_context(active_test=False):
            if not user.ei_auto_configured:
                continue
            is_administrator = bool(administrator and user == administrator)
            account_user = user._ei_has_any_group(
                (
                    "account.group_account_readonly",
                    "account.group_account_user",
                    "account.group_account_manager",
                )
            )
            account_manager = user._ei_has_any_group(
                ("account.group_account_manager",)
            )
            hr_user = user._ei_has_any_group(("hr.group_hr_user",))
            hr_manager = user._ei_has_any_group(("hr.group_hr_manager",))
            forecast_manager = user._ei_has_any_group(("stock.group_stock_manager",))
            alert_manager = user._ei_has_any_group(
                (
                    "account.group_account_manager",
                    "sales_team.group_sale_manager",
                    "stock.group_stock_manager",
                    "purchase.group_purchase_manager",
                    "hr.group_hr_manager",
                    "mrp.group_mrp_manager",
                )
            )
            user.with_context(
                _ei_skip_role_sync=True,
                _ei_auto_configuration_write=True,
            ).write(
                {
                    "ei_financial_access": "detail"
                    if is_administrator or account_manager
                    else ("summary" if account_user else "none"),
                    "ei_hr_access": "payroll"
                    if is_administrator
                    else ("employee" if hr_manager else ("statistics" if hr_user else "none")),
                    "ei_can_forecast": is_administrator or forecast_manager,
                    "ei_can_manage_alerts": is_administrator or alert_manager,
                    "ei_can_manage_kpis": is_administrator,
                }
            )
        return result

    @api.model
    def _ei_setup_extended_defaults(self):
        self._ei_setup_core_defaults()
        users = self.sudo().with_context(active_test=False).search(
            [("active", "=", True), ("share", "=", False)]
        )
        users._ei_sync_role_based_access()

        Profile = self.env["executive.intelligence.access.profile"].sudo()
        dashboards = {
            code: self._ei_dashboard(code)
            for code in (
                "executive",
                "finance",
                "sales",
                "purchase",
                "inventory",
                "product",
                "forecast",
                "hr",
                "operations",
                "risk",
            )
        }
        dashboards["executive"].sudo().write({"sensitivity": "financial"})
        profile_specs = (
            ("finance_viewer", "مستخدم التحليل المالي", ("finance",), {"financial_access": "summary"}),
            ("finance_manager", "مدير التحليل المالي", ("finance",), {"financial_access": "detail", "can_drilldown": True, "can_export": True}),
            ("sales_viewer", "مستخدم تحليل المبيعات", ("sales",), {}),
            ("sales_manager", "مدير تحليل المبيعات", ("sales",), {"can_drilldown": True, "can_export": True}),
            ("product_viewer", "مستخدم تحليل المنتجات", ("product",), {}),
            ("product_manager", "مدير تحليل المنتجات", ("product", "forecast", "risk"), {"can_drilldown": True, "can_export": True, "can_forecast": True, "can_manage_alerts": True}),
            ("hr_viewer", "مستخدم مؤشرات الموارد البشرية", ("hr",), {"hr_access": "statistics"}),
            ("hr_manager", "مدير مؤشرات الموارد البشرية", ("hr",), {"hr_access": "employee", "can_drilldown": True, "can_export": True}),
            ("operations_viewer", "مستخدم مؤشرات العمليات", ("operations",), {}),
            ("operations_manager", "مدير مؤشرات العمليات", ("operations", "forecast", "risk"), {"can_drilldown": True, "can_export": True, "can_forecast": True, "can_manage_alerts": True}),
            ("executive_manager", "الإدارة التنفيذية الشاملة", tuple(dashboards), {"financial_access": "detail", "hr_access": "statistics", "can_drilldown": True, "can_export": True, "can_forecast": True, "can_manage_alerts": True, "can_manage_kpis": True}),
        )
        Warehouse = self.env["stock.warehouse"].sudo()
        for company in self.env["res.company"].sudo().search([]):
            company_warehouses = Warehouse.search([("company_id", "=", company.id)])
            for suffix, name, codes, permissions in profile_specs:
                auto_code = f"extended_{suffix}_company_{company.id}"
                values = {
                    "name": f"{name} — {company.name}",
                    "auto_code": auto_code,
                    "dashboard_ids": [(6, 0, [dashboards[code].id for code in codes])],
                    "company_ids": [(6, 0, company.ids)],
                    "warehouse_ids": [(6, 0, company_warehouses.ids)],
                    "financial_access": "none",
                    "hr_access": "none",
                    "can_drilldown": False,
                    "can_export": False,
                    "can_forecast": False,
                    "can_manage_alerts": False,
                    "can_manage_kpis": False,
                    **permissions,
                }
                profile = Profile.search([("auto_code", "=", auto_code)], limit=1)
                if profile:
                    profile.write(values)
                else:
                    Profile.create(values)
        return True


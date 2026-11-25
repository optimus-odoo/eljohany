from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _ei_automatic_dashboard_ids(self):
        dashboards = super()._ei_automatic_dashboard_ids()
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        purchase_group = self.env.ref("purchase.group_purchase_user")
        if (administrator and self == administrator) or purchase_group in self.groups_id:
            dashboards |= self.env.ref(
                "eljohany_executive_intelligence_core.dashboard_purchase"
            )
        return dashboards

    def _ei_automatic_manager_access(self):
        return super()._ei_automatic_manager_access() or self.env.ref(
            "purchase.group_purchase_manager"
        ) in self.groups_id

    @api.model
    def _ei_setup_purchase_defaults(self):
        self._ei_setup_core_defaults()
        self._ei_setup_inventory_defaults()
        dashboard = self.env.ref(
            "eljohany_executive_intelligence_core.dashboard_purchase"
        )
        center_group = self.env.ref(
            "eljohany_executive_intelligence_core.group_ei_user"
        )
        purchase_user_group = self.env.ref("purchase.group_purchase_user")
        purchase_manager_group = self.env.ref("purchase.group_purchase_manager")
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        warehouses = self.env["stock.warehouse"].sudo().search([])
        users = self.sudo().with_context(active_test=False).search(
            [
                ("active", "=", True),
                ("share", "=", False),
                ("groups_id", "in", purchase_user_group.id),
            ]
        )
        if administrator:
            users |= administrator

        for user in users:
            is_administrator = administrator and user == administrator
            is_unconfigured = not user.ei_access_profile_id and not user.ei_custom_access
            if not (is_administrator or user.ei_auto_configured or is_unconfigured):
                continue
            user_warehouses = user._ei_automatic_warehouse_scope(
                user.company_ids.ids
            )
            user.sudo().with_context(
                _ei_skip_role_sync=True,
                _ei_auto_configuration_write=True,
            ).write(
                {
                    "groups_id": [(4, center_group.id)],
                    "ei_access_profile_id": False,
                    "ei_custom_access": True,
                    "ei_auto_configured": True,
                    "ei_dashboard_ids": [(4, dashboard.id)],
                    "ei_company_ids": [(6, 0, user.company_ids.ids)],
                    "ei_warehouse_ids": [(6, 0, user_warehouses.ids)],
                    "ei_can_drilldown": is_administrator
                    or purchase_manager_group in user.groups_id,
                    "ei_can_export": is_administrator
                    or purchase_manager_group in user.groups_id,
                }
            )
        users._ei_sync_role_based_access()

        Profile = self.env["executive.intelligence.access.profile"].sudo()
        for company in self.env["res.company"].sudo().search([]):
            company_warehouses = warehouses.filtered(
                lambda warehouse: warehouse.company_id == company
            )
            for role, name, manager in (
                ("viewer", "مستخدم لوحة المشتريات", False),
                ("manager", "مدير لوحة المشتريات", True),
            ):
                code = f"purchase_{role}_company_{company.id}"
                profile = Profile.search([("auto_code", "=", code)], limit=1)
                values = {
                    "name": f"{name} — {company.name}",
                    "auto_code": code,
                    "dashboard_ids": [(6, 0, dashboard.ids)],
                    "company_ids": [(6, 0, company.ids)],
                    "warehouse_ids": [(6, 0, company_warehouses.ids)],
                    "can_drilldown": manager,
                    "can_export": manager,
                }
                if profile:
                    profile.write(values)
                else:
                    Profile.create(values)
        return True

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    ei_warehouse_ids = fields.Many2many(
        "stock.warehouse",
        "ei_user_warehouse_rel",
        "user_id",
        "warehouse_id",
        string="Analytics Warehouses",
    )

    @api.constrains("ei_warehouse_ids", "company_ids")
    def _check_ei_warehouse_companies(self):
        for user in self:
            allowed_company_ids = set(user.company_ids.ids)
            invalid = user.ei_warehouse_ids.filtered(
                lambda warehouse: warehouse.company_id.id not in allowed_company_ids
            )
            if invalid:
                raise ValidationError(
                    _(
                        "Analytics warehouses must belong to the user's "
                        "allowed companies."
                    )
                )

    def _ei_effective_access(self):
        result = super()._ei_effective_access()
        self.ensure_one()
        user = self.sudo()
        if not user.ei_custom_access and user.ei_access_profile_id:
            configured_ids = set(user.ei_access_profile_id.warehouse_ids.ids)
        elif user.ei_custom_access:
            configured_ids = set(user.ei_warehouse_ids.ids)
        else:
            configured_ids = set()

        # Administrative scope metadata only; business rows are never queried
        # with sudo by the analytics providers.
        warehouses = self.env["stock.warehouse"].sudo().browse(configured_ids).exists()
        configured_ids = {
            warehouse.id
            for warehouse in warehouses
            if warehouse.company_id.id in result["company_ids"]
        }

        automatic_warehouses = user._ei_automatic_warehouse_scope(
            result["company_ids"]
        )
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        is_administrator = bool(administrator and user == administrator)
        if not configured_ids and (user.ei_auto_configured or is_administrator):
            # Self-heal stale automatic configurations at request time. This is
            # metadata only; every provider still reads business rows without
            # sudo and remains subject to native Odoo access rules.
            configured_ids = set(automatic_warehouses.ids)

        restriction_group = self.env.ref(
            "user_warehouse_restriction.user_warehouse_restriction_group_user",
            raise_if_not_found=False,
        )
        if (
            restriction_group
            and restriction_group in user.groups_id
            and "restrict_location" in user._fields
            and user.restrict_location
            and not is_administrator
        ):
            configured_ids &= set(automatic_warehouses.ids)

        result["warehouse_ids"] = sorted(configured_ids)
        return result

    def _ei_automatic_warehouse_scope(self, company_ids):
        """Return the safe native warehouse scope for automatic analytics."""
        self.ensure_one()
        user = self.sudo()
        Warehouse = self.env["stock.warehouse"].sudo()
        warehouses = Warehouse.search(
            [("company_id", "in", [int(company_id) for company_id in company_ids])]
        )
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        if administrator and user == administrator:
            return warehouses

        restriction_group = self.env.ref(
            "user_warehouse_restriction.user_warehouse_restriction_group_user",
            raise_if_not_found=False,
        )
        if (
            restriction_group
            and restriction_group in user.groups_id
            and "restrict_location" in user._fields
            and user.restrict_location
        ):
            assigned_ids = set()
            if "allowed_warehouse_ids" in user._fields:
                assigned_ids |= set(user.allowed_warehouse_ids.ids)
            if "user_ids" in Warehouse._fields:
                assigned_ids |= set(
                    warehouses.filtered(
                        lambda warehouse: user.id in warehouse.user_ids.ids
                    ).ids
                )
            warehouses = warehouses.filtered(
                lambda warehouse: warehouse.id in assigned_ids
            )
        return warehouses

    def _ei_automatic_dashboard_ids(self):
        dashboards = super()._ei_automatic_dashboard_ids()
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)
        stock_group = self.env.ref("stock.group_stock_user")
        if (administrator and self == administrator) or stock_group in self.groups_id:
            dashboards |= self.env.ref(
                "eljohany_executive_intelligence_core.dashboard_inventory"
            )
        return dashboards

    def _ei_automatic_manager_access(self):
        return super()._ei_automatic_manager_access() or self.env.ref(
            "stock.group_stock_manager"
        ) in self.groups_id

    @api.model
    def _ei_setup_inventory_defaults(self):
        self._ei_setup_core_defaults()
        dashboard = self.env.ref(
            "eljohany_executive_intelligence_core.dashboard_inventory"
        )
        center_group = self.env.ref(
            "eljohany_executive_intelligence_core.group_ei_user"
        )
        stock_user_group = self.env.ref("stock.group_stock_user")
        stock_manager_group = self.env.ref("stock.group_stock_manager")
        administrator = self.env.ref("base.user_admin", raise_if_not_found=False)

        warehouses = self.env["stock.warehouse"].sudo().search([])
        users = self.sudo().with_context(active_test=False).search(
            [
                ("active", "=", True),
                ("share", "=", False),
                ("groups_id", "in", stock_user_group.id),
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
                    or stock_manager_group in user.groups_id,
                    "ei_can_export": is_administrator
                    or stock_manager_group in user.groups_id,
                }
            )
        users._ei_sync_role_based_access()

        Profile = self.env["executive.intelligence.access.profile"].sudo()
        for company in self.env["res.company"].sudo().search([]):
            company_warehouses = warehouses.filtered(
                lambda warehouse: warehouse.company_id == company
            )
            for role, name, manager in (
                ("viewer", "مستخدم لوحة المخزون", False),
                ("manager", "مدير لوحة المخزون", True),
            ):
                code = f"inventory_{role}_company_{company.id}"
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


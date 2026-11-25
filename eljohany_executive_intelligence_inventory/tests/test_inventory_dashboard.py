from odoo import fields
from odoo.modules.module import get_module_resource
from odoo.tests.common import TransactionCase
from odoo.tools.translate import TranslationFileReader


class TestInventoryDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Inventory KPI Product", "detailed_type": "product"}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 10.0
        )
        dashboard = cls.env.ref(
            "eljohany_executive_intelligence_core.dashboard_inventory"
        )
        profile = cls.env["executive.intelligence.access.profile"].create(
            {
                "name": "Inventory KPI Viewer",
                "dashboard_ids": [(6, 0, dashboard.ids)],
                "company_ids": [(6, 0, cls.company.ids)],
                "warehouse_ids": [(6, 0, cls.warehouse.ids)],
            }
        )
        groups = [
            cls.env.ref("base.group_user").id,
            cls.env.ref("stock.group_stock_user").id,
            cls.env.ref("eljohany_executive_intelligence_core.group_ei_user").id,
        ]
        cls.viewer = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Inventory KPI Viewer",
                "login": "inventory.kpi.viewer",
                "email": "inventory.kpi.viewer@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, cls.company.ids)],
                "groups_id": [(6, 0, groups)],
                "ei_access_profile_id": profile.id,
            }
        )

    def test_inventory_dashboard_reports_real_quant(self):
        data = self.env["executive.intelligence.service"].with_user(
            self.viewer
        ).get_dashboard_data(
            "inventory",
            {
                "company_ids": self.company.ids,
                "warehouse_ids": self.warehouse.ids,
                "date_from": fields.Date.today(),
                "date_to": fields.Date.today(),
            },
        )
        cards = {card["key"]: card for card in data["cards"]}
        self.assertGreaterEqual(cards["stock_positions"]["value"], 1)
        table = data["tables"][0]
        row = next(row for row in table["rows"] if row["product"] == self.product.display_name)
        self.assertEqual(row["quantity"], "10.00")
        self.assertEqual(
            {chart["type"] for chart in data["charts"]}, {"bar", "gauge"}
        )
        warehouse_chart = next(
            chart
            for chart in data["charts"]
            if chart["key"] == "warehouse_stock_positions"
        )
        self.assertGreaterEqual(warehouse_chart["items"][0]["value"], 1)

    def test_bootstrap_exposes_inventory_provider(self):
        bootstrap = self.env["executive.intelligence.service"].with_user(
            self.viewer
        ).get_bootstrap()
        self.assertEqual(
            [dashboard["code"] for dashboard in bootstrap["dashboards"]],
            ["inventory"],
        )

    def test_arabic_translation_is_odoo_loadable(self):
        path = get_module_resource(
            "eljohany_executive_intelligence_inventory", "i18n", "ar_001.po"
        )
        rows = list(TranslationFileReader(path))
        self.assertGreaterEqual(len(rows), 25)
        translations = {row["src"]: row["value"] for row in rows}
        self.assertEqual(
            translations["Current quantities by warehouse and product"],
            "الكميات الحالية حسب المستودع والمنتج",
        )

    def test_stock_user_is_configured_automatically(self):
        stock_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Automatic Inventory User",
                "login": "automatic.inventory.user",
                "email": "automatic.inventory.user@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, self.company.ids)],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("stock.group_stock_user").id,
                        ],
                    )
                ],
            }
        )
        self.env["res.users"]._ei_setup_inventory_defaults()
        inventory_dashboard = self.env.ref(
            "eljohany_executive_intelligence_core.dashboard_inventory"
        )
        self.assertTrue(stock_user.ei_enabled)
        self.assertTrue(stock_user.ei_auto_configured)
        self.assertIn(inventory_dashboard, stock_user.ei_dashboard_ids)
        purchase_dashboard = self.env.ref(
            "eljohany_executive_intelligence_core.dashboard_purchase"
        )
        self.assertNotIn(purchase_dashboard, stock_user.ei_dashboard_ids)
        self.assertEqual(stock_user.ei_company_ids, stock_user.company_ids)
        self.assertIn(self.warehouse, stock_user.ei_warehouse_ids)
        self.assertTrue(
            self.env["executive.intelligence.access.profile"].search_count(
                [("auto_code", "=", f"inventory_viewer_company_{self.company.id}")]
            )
        )
        stock_user.write(
            {
                "ei_auto_configured": False,
                "ei_can_export": True,
            }
        )
        stock_user.write(
            {"groups_id": [(3, self.env.ref("stock.group_stock_user").id)]}
        )
        self.assertFalse(stock_user.ei_auto_configured)
        self.assertTrue(stock_user.ei_can_export)
        self.assertIn(inventory_dashboard, stock_user.ei_dashboard_ids)

    def test_automatic_empty_warehouse_scope_self_heals(self):
        stock_user = self.env["res.users"].with_context(
            no_reset_password=True
        ).create(
            {
                "name": "Automatic Scope Recovery User",
                "login": "automatic.scope.recovery.user",
                "email": "automatic.scope.recovery@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, self.company.ids)],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("stock.group_stock_user").id,
                        ],
                    )
                ],
            }
        )
        self.env["res.users"]._ei_setup_inventory_defaults()
        restriction_group = self.env.ref(
            "user_warehouse_restriction.user_warehouse_restriction_group_user",
            raise_if_not_found=False,
        )
        if restriction_group and "restrict_location" in stock_user._fields:
            stock_user.with_context(
                _ei_auto_configuration_write=True,
                _ei_skip_role_sync=True,
            ).write(
                {
                    "groups_id": [(4, restriction_group.id)],
                    "restrict_location": False,
                }
            )
        stock_user.with_context(
            _ei_auto_configuration_write=True,
            _ei_skip_role_sync=True,
        ).write({"ei_warehouse_ids": [(5, 0, 0)]})

        access = stock_user._ei_effective_access()

        self.assertTrue(stock_user.ei_auto_configured)
        self.assertIn(self.warehouse.id, access["warehouse_ids"])

        if restriction_group and "restrict_location" in stock_user._fields:
            stock_user.with_context(
                _ei_auto_configuration_write=True,
                _ei_skip_role_sync=True,
            ).write(
                {
                    "restrict_location": True,
                    "allowed_warehouse_ids": [(5, 0, 0)],
                    "ei_warehouse_ids": [(5, 0, 0)],
                }
            )
            self.assertEqual(
                stock_user._ei_effective_access()["warehouse_ids"], []
            )
            stock_user.with_context(
                _ei_auto_configuration_write=True,
                _ei_skip_role_sync=True,
            ).write({"restrict_location": False})

        stock_user.with_context(_ei_skip_role_sync=True).write(
            {"ei_warehouse_ids": [(6, 0, self.warehouse.ids)]}
        )
        self.assertFalse(stock_user.ei_auto_configured)

    def test_administrator_empty_warehouse_scope_self_heals(self):
        self.env["res.users"]._ei_setup_inventory_defaults()
        administrator = self.env.ref("base.user_admin")
        administrator.with_context(
            _ei_auto_configuration_write=True,
            _ei_skip_role_sync=True,
        ).write({"ei_warehouse_ids": [(5, 0, 0)]})

        access = administrator._ei_effective_access()

        self.assertIn(self.warehouse.id, access["warehouse_ids"])


from datetime import timedelta

from odoo import fields
from odoo.modules.module import get_module_resource
from odoo.tests.common import TransactionCase
from odoo.tools.translate import TranslationFileReader


class TestPurchaseDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.partner = cls.env["res.partner"].create({"name": "KPI Supplier"})
        cls.product = cls.env["product.product"].create(
            {"name": "KPI Product", "detailed_type": "product", "purchase_ok": True}
        )
        cls.order = cls.env["purchase.order"].create(
            {
                "partner_id": cls.partner.id,
                "company_id": cls.company.id,
                "picking_type_id": cls.warehouse.in_type_id.id,
                "date_order": fields.Datetime.now(),
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": cls.product.display_name,
                            "product_id": cls.product.id,
                            "product_qty": 5.0,
                            "product_uom": cls.product.uom_po_id.id,
                            "price_unit": 20.0,
                            "date_planned": fields.Datetime.now() + timedelta(days=3),
                        },
                    )
                ],
            }
        )
        cls.order.button_confirm()
        purchase_dashboard = cls.env.ref(
            "eljohany_executive_intelligence_core.dashboard_purchase"
        )
        cls.profile = cls.env["executive.intelligence.access.profile"].create(
            {
                "name": "Purchase KPI Viewer",
                "dashboard_ids": [(6, 0, purchase_dashboard.ids)],
                "company_ids": [(6, 0, cls.company.ids)],
                "warehouse_ids": [(6, 0, cls.warehouse.ids)],
            }
        )
        groups = [
            cls.env.ref("base.group_user").id,
            cls.env.ref("purchase.group_purchase_user").id,
            cls.env.ref("stock.group_stock_user").id,
            cls.env.ref("eljohany_executive_intelligence_core.group_ei_user").id,
        ]
        cls.viewer = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Purchase KPI Viewer",
                "login": "purchase.kpi.viewer",
                "email": "purchase.kpi.viewer@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, cls.company.ids)],
                "groups_id": [(6, 0, groups)],
                "ei_access_profile_id": cls.profile.id,
            }
        )

    def test_purchase_dashboard_uses_real_confirmed_order(self):
        data = self.env["executive.intelligence.service"].with_user(
            self.viewer
        ).get_dashboard_data(
            "purchase",
            {
                "company_ids": self.company.ids,
                "warehouse_ids": self.warehouse.ids,
                "date_from": fields.Date.today(),
                "date_to": fields.Date.today(),
            },
        )
        cards = {card["key"]: card for card in data["cards"]}
        self.assertEqual(cards["confirmed_order_count"]["value"], 1)
        self.assertEqual(cards["open_purchase_orders"]["value"], 1)
        self.assertAlmostEqual(
            cards[f"confirmed_value_{self.company.currency_id.id}"]["value"],
            100.0,
            places=2,
        )
        supplier_table = next(
            table for table in data["tables"] if table["key"] == "top_suppliers"
        )
        self.assertEqual(supplier_table["rows"][0]["supplier"], self.partner.name)
        self.assertEqual(
            {chart["type"] for chart in data["charts"]},
            {"line", "bar", "gauge"},
        )
        trend = next(
            chart
            for chart in data["charts"]
            if chart["key"] == "monthly_purchase_order_trend"
        )
        self.assertEqual(sum(item["value"] for item in trend["items"]), 1)
        self.assertIn("comparison", cards["confirmed_order_count"])

    def test_bootstrap_exposes_purchase_provider(self):
        bootstrap = self.env["executive.intelligence.service"].with_user(
            self.viewer
        ).get_bootstrap()
        self.assertEqual(
            [dashboard["code"] for dashboard in bootstrap["dashboards"]],
            ["purchase"],
        )

    def test_unconfigured_warehouse_returns_safe_empty_scope(self):
        self.profile.warehouse_ids = False
        service = self.env["executive.intelligence.service"].with_user(self.viewer)
        data = service.get_dashboard_data(
            "purchase",
            {
                "company_ids": self.company.ids,
                "date_from": fields.Date.today(),
                "date_to": fields.Date.today(),
            },
        )
        self.assertEqual(data["status"], "warehouse_scope_unavailable")
        self.assertEqual(data["cards"], [])
        self.assertEqual(data["charts"], [])
        self.assertEqual(data["tables"], [])

    def test_arabic_translation_is_odoo_loadable(self):
        path = get_module_resource(
            "eljohany_executive_intelligence_purchase", "i18n", "ar_001.po"
        )
        rows = list(TranslationFileReader(path))
        self.assertGreaterEqual(len(rows), 28)
        translations = {row["src"]: row["value"] for row in rows}
        self.assertEqual(
            translations["Confirmed purchase orders"],
            "أوامر الشراء المؤكدة",
        )

    def test_purchase_user_is_configured_automatically(self):
        purchase_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Automatic Purchase User",
                "login": "automatic.purchase.user",
                "email": "automatic.purchase.user@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, self.company.ids)],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("purchase.group_purchase_user").id,
                        ],
                    )
                ],
            }
        )
        self.env["res.users"]._ei_setup_purchase_defaults()
        purchase_dashboard = self.env.ref(
            "eljohany_executive_intelligence_core.dashboard_purchase"
        )
        self.assertTrue(purchase_user.ei_enabled)
        self.assertTrue(purchase_user.ei_auto_configured)
        self.assertIn(purchase_dashboard, purchase_user.ei_dashboard_ids)
        inventory_dashboard = self.env.ref(
            "eljohany_executive_intelligence_core.dashboard_inventory"
        )
        self.assertNotIn(inventory_dashboard, purchase_user.ei_dashboard_ids)
        self.assertEqual(purchase_user.ei_company_ids, purchase_user.company_ids)
        self.assertIn(self.warehouse, purchase_user.ei_warehouse_ids)
        purchase_user.with_context(
            _ei_auto_configuration_write=True,
            _ei_skip_role_sync=True,
        ).write({"ei_warehouse_ids": [(5, 0, 0)]})
        bootstrap = self.env["executive.intelligence.service"].with_user(
            purchase_user
        ).get_bootstrap()
        self.assertIn(
            self.warehouse.id,
            [warehouse["id"] for warehouse in bootstrap["warehouses"]],
        )
        self.assertTrue(
            self.env["executive.intelligence.access.profile"].search_count(
                [("auto_code", "=", f"purchase_viewer_company_{self.company.id}")]
            )
        )


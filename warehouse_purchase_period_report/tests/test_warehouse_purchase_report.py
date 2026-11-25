# -*- coding: utf-8 -*-

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools.translate import TranslationFileReader


class TestWarehousePurchaseReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.other_company = cls.env["res.company"].sudo().create(
            {"name": "Warehouse Purchase Report Other Company"}
        )
        cls.other_warehouse = cls.env["stock.warehouse"].sudo().create(
            {
                "name": "Other Warehouse",
                "code": "OWH",
                "company_id": cls.other_company.id,
            }
        )
        template = cls.env["product.template"].create(
            {
                "name": "Warehouse Purchase Report Product",
                "type": "product",
                "standard_price": 5.0,
                "company_id": cls.company.id,
            }
        )
        cls.product = template.product_variant_id
        cls.supplier_location = cls.env.ref("stock.stock_location_suppliers")
        cls.customer_location = cls.env.ref("stock.stock_location_customers")

    def _wizard(self, **overrides):
        today = fields.Date.context_today(self.env.user)
        values = {
            "company_id": self.company.id,
            "warehouse_ids": [(6, 0, self.warehouse.ids)],
            "date_from": today - timedelta(days=7),
            "date_to": today,
        }
        values.update(overrides)
        return self.env["warehouse.purchase.report.wizard"].create(values)

    def test_ar_translation_catalog_is_odoo_compatible(self):
        translation_path = (
            Path(__file__).resolve().parents[1] / "i18n" / "ar.po"
        )

        translations = list(TranslationFileReader(str(translation_path), "po"))

        self.assertTrue(translations)
        self.assertEqual(
            {translation["module"] for translation in translations},
            {"warehouse_purchase_period_report"},
        )

    def test_reversed_period_is_rejected(self):
        today = fields.Date.context_today(self.env.user)
        with self.assertRaises(ValidationError):
            self._wizard(date_from=today, date_to=today - timedelta(days=1))

    def test_warehouse_must_belong_to_selected_company(self):
        with self.assertRaises(ValidationError):
            self._wizard(warehouse_ids=[(6, 0, self.other_warehouse.ids)])

    def test_period_bounds_are_half_open_and_use_user_timezone(self):
        wizard = self._wizard()
        start_utc, end_utc = wizard._utc_period_bounds()

        self.assertLess(start_utc, end_utc)
        self.assertEqual(
            fields.Datetime.to_datetime(end_utc)
            - fields.Datetime.to_datetime(start_utc),
            timedelta(days=8),
        )

    def test_empty_activity_returns_no_lines(self):
        wizard = self._wizard()
        model_class = type(wizard)
        with patch.object(
            model_class,
            "_warehouse_location_map",
            return_value={1: self.warehouse.id},
        ), patch.object(
            model_class,
            "_get_opening_move_lines",
            return_value=self.env["stock.move.line"],
        ), patch.object(
            model_class,
            "_get_period_move_lines",
            return_value=self.env["stock.move.line"],
        ):
            self.assertEqual(wizard._prepare_lines(), [])

    def test_receipt_is_grouped_by_warehouse_and_product_uom(self):
        move = self.env["stock.move"].create(
            {
                "name": "Warehouse Purchase Report Receipt",
                "company_id": self.company.id,
                "product_id": self.product.id,
                "product_uom": self.product.uom_id.id,
                "product_uom_qty": 10.0,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
            }
        )
        move_line = self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "quantity": 10.0,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
            }
        )
        wizard = self._wizard()
        model_class = type(wizard)
        with patch.object(
            model_class,
            "_warehouse_location_map",
            return_value={self.warehouse.lot_stock_id.id: self.warehouse.id},
        ), patch.object(
            model_class,
            "_get_opening_move_lines",
            return_value=self.env["stock.move.line"],
        ), patch.object(
            model_class,
            "_get_period_move_lines",
            return_value=move_line,
        ), patch.object(
            model_class,
            "_cost_by_move",
            return_value=({move.id: 75.0}, {move.id: "purchase_order"}),
        ):
            lines = wizard._prepare_lines()

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["warehouse_id"], self.warehouse.id)
        self.assertEqual(lines[0]["uom_id"], self.product.uom_id.id)
        self.assertEqual(lines[0]["period_quantity"], 10.0)
        self.assertEqual(lines[0]["average_cost"], 7.5)
        self.assertEqual(lines[0]["total_value"], 75.0)
        self.assertFalse(lines[0]["estimated_cost"])
        self.assertEqual(lines[0]["cost_source"], "purchase_order")

    def test_grand_total_sums_line_total_values(self):
        wizard = self._wizard()
        self.env["warehouse.purchase.report.line"].create(
            [
                {
                    "wizard_id": wizard.id,
                    "warehouse_id": self.warehouse.id,
                    "uom_id": self.product.uom_id.id,
                    "period_quantity": 10.0,
                    "average_cost": 7.5,
                    "total_value": 75.0,
                    "cost_source": "inventory_valuation",
                },
                {
                    "wizard_id": wizard.id,
                    "warehouse_id": self.warehouse.id,
                    "uom_id": self.product.uom_id.id,
                    "period_quantity": 5.0,
                    "average_cost": 5.0,
                    "total_value": 25.0,
                    "cost_source": "inventory_valuation",
                },
            ]
        )

        self.assertEqual(wizard.total_value, 100.0)

    def test_closing_quantity_and_opening_balance_average_cost(self):
        opening_move = self.env["stock.move"].create(
            {
                "name": "Warehouse Report Opening Balance",
                "company_id": self.company.id,
                "product_id": self.product.id,
                "product_uom": self.product.uom_id.id,
                "product_uom_qty": 20.0,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
            }
        )
        opening_move_line = self.env["stock.move.line"].create(
            {
                "move_id": opening_move.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "quantity": 20.0,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
            }
        )
        movement_specs = [
            ("Purchase", 10.0, self.supplier_location, self.warehouse.lot_stock_id),
            ("Sale", 4.0, self.warehouse.lot_stock_id, self.customer_location),
            (
                "Sale Return",
                2.0,
                self.customer_location,
                self.warehouse.lot_stock_id,
            ),
            (
                "Purchase Return",
                1.0,
                self.warehouse.lot_stock_id,
                self.supplier_location,
            ),
        ]
        move_lines = self.env["stock.move.line"]
        costs = {}
        sources = {}
        movement_costs = (50.0, 32.0, 18.0, 6.0)
        for (name, quantity, source, destination), movement_cost in zip(
            movement_specs, movement_costs
        ):
            move = self.env["stock.move"].create(
                {
                    "name": "Warehouse Report %s" % name,
                    "company_id": self.company.id,
                    "product_id": self.product.id,
                    "product_uom": self.product.uom_id.id,
                    "product_uom_qty": quantity,
                    "location_id": source.id,
                    "location_dest_id": destination.id,
                }
            )
            move_line = self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "product_id": self.product.id,
                    "product_uom_id": self.product.uom_id.id,
                    "quantity": quantity,
                    "location_id": source.id,
                    "location_dest_id": destination.id,
                }
            )
            move_lines |= move_line
            costs[move.id] = movement_cost
            sources[move.id] = "inventory_valuation"

        wizard = self._wizard()
        model_class = type(wizard)
        with patch.object(
            model_class,
            "_warehouse_location_map",
            return_value={self.warehouse.lot_stock_id.id: self.warehouse.id},
        ), patch.object(
            model_class,
            "_get_opening_move_lines",
            return_value=opening_move_line,
        ), patch.object(
            model_class,
            "_get_period_move_lines",
            return_value=move_lines,
        ), patch.object(
            model_class,
            "_opening_cost_by_product",
            return_value=(
                {self.product.id: 4.0},
                {self.product.id: "inventory_valuation"},
            ),
        ), patch.object(
            model_class,
            "_cost_by_move",
            return_value=(costs, sources),
        ):
            lines = wizard._prepare_lines()

        self.assertEqual(len(lines), 1)
        # 20 opening + 10 purchases - 4 sales + 2 sales returns - 1 return.
        self.assertEqual(lines[0]["period_quantity"], 27.0)
        # (20 * 4 opening value + 50 purchases - 6 purchase returns)
        # / (20 opening quantity + 10 purchases - 1 purchase return).
        self.assertEqual(lines[0]["average_cost"], 4.28)
        self.assertEqual(lines[0]["total_value"], 115.56)

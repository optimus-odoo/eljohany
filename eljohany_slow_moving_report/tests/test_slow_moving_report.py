# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSlowMovingProductsReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.location = cls.env["stock.location"].create(
            {
                "name": "Slow Moving Test Stock",
                "usage": "internal",
                "company_id": cls.company.id,
            }
        )
        cls.child_location = cls.env["stock.location"].create(
            {
                "name": "Slow Moving Test Shelf",
                "usage": "internal",
                "location_id": cls.location.id,
                "company_id": cls.company.id,
            }
        )
        template = cls.env["product.template"].create(
            {
                "name": "Slow Moving Test Product",
                "type": "product",
                "standard_price": 12.5,
                "company_id": cls.company.id,
            }
        )
        cls.product = template.product_variant_id
        cls.other_company = cls.env["res.company"].sudo().create(
            {"name": "Slow Moving Other Company"}
        )
        other_template = cls.env["product.template"].sudo().create(
            {
                "name": "Other Company Slow Moving Product",
                "type": "product",
                "company_id": cls.other_company.id,
            }
        )
        cls.other_company_product = other_template.product_variant_id

    def _wizard(self, **overrides):
        values = {
            "company_id": self.company.id,
            "location_ids": [(6, 0, self.location.ids)],
            "report_date": fields.Date.context_today(self.env.user),
            "inactivity_days": 90,
            "product_ids": [(6, 0, self.product.ids)],
        }
        values.update(overrides)
        return self.env["eljohany.slow.moving.report.wizard"].create(values)

    def _prepare_with_dates(self, wizard, first_entry, last_delivery=False):
        product_id = self.product.id
        model_class = type(wizard)
        with patch.object(
            model_class,
            "_get_quantity_by_product",
            return_value={product_id: 10.0},
        ), patch.object(
            model_class,
            "_get_last_customer_delivery_dates",
            return_value={product_id: last_delivery} if last_delivery else {},
        ), patch.object(
            model_class,
            "_get_stock_entry_dates",
            return_value=(
                {product_id: first_entry},
                {product_id: first_entry},
            ),
        ), patch.object(
            model_class,
            "_get_period_customer_quantities",
            return_value=({product_id: 5.0}, {product_id: 2.0}),
        ):
            return wizard._prepare_lines()

    def test_new_never_sold_product_is_not_stagnant(self):
        wizard = self._wizard()
        first_entry = datetime.combine(
            wizard.report_date - timedelta(days=10), datetime.min.time()
        )

        lines = self._prepare_with_dates(wizard, first_entry)

        self.assertFalse(lines)

    def test_products_are_limited_to_selected_company(self):
        wizard = self._wizard()
        wizard.sudo().product_ids = self.product | self.other_company_product

        products = wizard.sudo()._get_products()

        self.assertIn(self.product, products)
        self.assertNotIn(self.other_company_product, products)

    def test_zero_balance_product_is_not_reported(self):
        wizard = self._wizard()
        model_class = type(wizard)
        with patch.object(
            model_class,
            "_get_quantity_by_product",
            return_value={self.product.id: 0.0},
        ), patch.object(
            model_class,
            "_get_last_customer_delivery_dates",
        ) as last_delivery:
            lines = wizard._prepare_lines()

        self.assertFalse(lines)
        last_delivery.assert_not_called()

    def test_old_never_sold_product_is_reported(self):
        wizard = self._wizard()
        first_entry = datetime.combine(
            wizard.report_date - timedelta(days=100), datetime.min.time()
        )

        lines = self._prepare_with_dates(wizard, first_entry)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["status"], "never_sold")
        self.assertEqual(lines[0]["days_inactive"], 100)
        self.assertEqual(lines[0]["qty_on_hand"], 10.0)
        self.assertEqual(lines[0]["stock_value"], 125.0)
        self.assertEqual(lines[0]["qty_delivered_period"], 5.0)
        self.assertEqual(lines[0]["qty_returned_period"], 2.0)
        self.assertEqual(lines[0]["net_qty_sold_period"], 3.0)

    def test_sales_are_limited_to_the_selected_period(self):
        wizard = self._wizard(
            sales_date_from=fields.Date.context_today(self.env.user)
            - timedelta(days=30),
            sales_date_to=fields.Date.context_today(self.env.user)
            - timedelta(days=5),
        )
        period_start, period_end = wizard._sales_period_bounds()
        model_class = type(wizard)

        with patch.object(
            model_class,
            "_read_quantity_groups",
            side_effect=[{self.product.id: 8.0}, {self.product.id: 2.0}],
        ) as grouped_read:
            delivered, returned = wizard._get_period_customer_quantities(
                self.product,
                self.location.ids,
                period_start,
                period_end,
            )

        self.assertEqual(delivered[self.product.id], 8.0)
        self.assertEqual(returned[self.product.id], 2.0)
        for call in grouped_read.call_args_list:
            domain = call.args[0]
            self.assertIn(("date", ">=", period_start), domain)
            self.assertIn(("date", "<=", period_end), domain)

    def test_historical_report_defaults_sales_period_to_its_year(self):
        report_date = fields.Date.context_today(self.env.user).replace(
            year=fields.Date.context_today(self.env.user).year - 1,
            month=6,
            day=30,
        )

        wizard = self._wizard(report_date=report_date)

        self.assertEqual(wizard.sales_date_to, report_date)
        self.assertEqual(
            wizard.sales_date_from,
            report_date.replace(month=1, day=1),
        )

    def test_recent_customer_delivery_excludes_product(self):
        wizard = self._wizard()
        first_entry = datetime.combine(
            wizard.report_date - timedelta(days=200), datetime.min.time()
        )
        last_delivery = datetime.combine(
            wizard.report_date - timedelta(days=20), datetime.min.time()
        )

        lines = self._prepare_with_dates(wizard, first_entry, last_delivery)

        self.assertFalse(lines)

    def test_very_stagnant_uses_last_delivery(self):
        wizard = self._wizard()
        first_entry = datetime.combine(
            wizard.report_date - timedelta(days=300), datetime.min.time()
        )
        last_delivery = datetime.combine(
            wizard.report_date - timedelta(days=190), datetime.min.time()
        )

        lines = self._prepare_with_dates(wizard, first_entry, last_delivery)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["status"], "very_stagnant")
        self.assertEqual(lines[0]["days_inactive"], 190)

    def test_child_locations_are_included_only_when_requested(self):
        wizard = self._wizard(include_child_locations=True)
        self.assertIn(self.child_location.id, wizard._get_location_ids())

        wizard.include_child_locations = False
        self.assertNotIn(self.child_location.id, wizard._get_location_ids())

    def test_balance_subtracts_moves_leaving_selected_locations(self):
        wizard = self._wizard()
        model_class = type(wizard)
        cutoff = wizard._report_cutoff()

        with patch.object(
            model_class,
            "_read_quantity_groups",
            side_effect=[{self.product.id: 15.0}, {self.product.id: 5.0}],
        ) as grouped_read:
            result = wizard._get_quantity_by_product(
                self.product,
                self.location.ids,
                cutoff,
            )

        self.assertEqual(result[self.product.id], 10.0)
        incoming_domain = grouped_read.call_args_list[0].args[0]
        outgoing_domain = grouped_read.call_args_list[1].args[0]
        self.assertIn(("location_dest_id", "in", self.location.ids), incoming_domain)
        self.assertIn(("location_id", "in", self.location.ids), outgoing_domain)

    def test_future_report_date_is_rejected(self):
        wizard = self._wizard(
            report_date=fields.Date.context_today(self.env.user) + timedelta(days=1)
        )
        with self.assertRaises(UserError):
            wizard._validate_report_options()

    def test_non_positive_inactivity_days_are_rejected(self):
        with self.assertRaises(ValidationError):
            self._wizard(inactivity_days=0)

    def test_reversed_sales_period_is_rejected(self):
        report_date = fields.Date.context_today(self.env.user)
        with self.assertRaises(ValidationError):
            self._wizard(
                sales_date_from=report_date,
                sales_date_to=report_date - timedelta(days=1),
            )

    def test_sales_period_cannot_end_after_report_date(self):
        report_date = fields.Date.context_today(self.env.user) - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self._wizard(
                report_date=report_date,
                sales_date_from=report_date,
                sales_date_to=report_date + timedelta(days=1),
            )

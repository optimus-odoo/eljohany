from datetime import datetime
from pathlib import Path

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestPosSalesMarginReport(TransactionCase):
    def _create_wizard(self, **values):
        defaults = {
            "company_id": self.env.company.id,
            "date_from": datetime(2026, 10, 19, 8, 30, 0),
            "date_to": datetime(2026, 10, 19, 18, 45, 0),
        }
        defaults.update(values)
        return self.env["pos.sales.margin.report.wizard"].create(defaults)

    def test_invalid_date_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_wizard(
                date_from=datetime(2026, 10, 20, 8, 0, 0),
                date_to=datetime(2026, 10, 19, 18, 0, 0),
            )

    def test_at_least_one_pos_is_required_server_side(self):
        wizard = self._create_wizard()
        with self.assertRaises(UserError):
            wizard._validate_report_options()

    def test_selected_datetimes_are_used_as_exact_inclusive_utc_bounds(self):
        wizard = self._create_wizard(
            date_from=datetime(2026, 10, 18, 21, 30, 0),
            date_to=datetime(2026, 10, 19, 15, 45, 0),
        ).with_context(tz="Asia/Riyadh")
        start_utc, end_utc = wizard._get_utc_datetime_bounds()
        self.assertEqual(start_utc, "2026-10-18 21:30:00")
        self.assertEqual(end_utc, "2026-10-19 15:45:00")
        self.assertEqual(
            wizard._format_report_datetime(wizard.date_from),
            "2026-10-19 00:30:00",
        )
        self.assertEqual(
            wizard._format_report_datetime(wizard.date_to),
            "2026-10-19 18:45:00",
        )

    def test_report_domains_include_orders_at_the_selected_end_time(self):
        wizard = self._create_wizard()
        self.assertIn(
            ("date", "<=", "2026-10-19 18:45:00"),
            wizard._get_report_domain(),
        )
        self.assertIn(
            ("order_id.date_order", "<=", "2026-10-19 18:45:00"),
            wizard._get_order_line_domain(),
        )

    def test_requested_amounts_and_margin_percentage(self):
        wizard = self._create_wizard()
        lines = wizard._build_lines_from_groups(
            [
                {
                    "product_id": (10, "Test Product"),
                    "product_qty": 3.0,
                    "price_sub_total": 100.0,
                    "total_discount": 10.0,
                    "price_total": 103.5,
                    "margin": 30.0,
                }
            ],
            {10: 3.75},
        )
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line["quantity"], 3.75)
        self.assertEqual(line["gross_total"], 100.0)
        self.assertEqual(line["discounts"], 10.0)
        self.assertEqual(line["net_total"], 90.0)
        self.assertEqual(line["tax"], 13.5)
        self.assertEqual(line["grand_total"], 103.5)
        self.assertEqual(line["margin"], 30.0)
        self.assertAlmostEqual(line["margin_percent"], 33.3333333333)

    def test_total_margin_percentage_uses_aggregate_net_sales(self):
        wizard = self._create_wizard()
        lines = [
            {
                "quantity": 2.0,
                "gross_total": 100.0,
                "discounts": 0.0,
                "net_total": 100.0,
                "tax": 15.0,
                "grand_total": 115.0,
                "margin": 40.0,
            },
            {
                "quantity": 1.0,
                "gross_total": 50.0,
                "discounts": 0.0,
                "net_total": 50.0,
                "tax": 7.5,
                "grand_total": 57.5,
                "margin": 10.0,
            },
        ]
        totals = wizard._get_totals(lines)
        self.assertEqual(totals["net_total"], 150.0)
        self.assertEqual(totals["margin"], 50.0)
        self.assertAlmostEqual(totals["margin_percent"], 33.3333333333)

    def test_margin_is_converted_per_order_currency_rate(self):
        wizard = self._create_wizard()
        quantity_by_product, margin_by_product = (
            wizard._aggregate_quantity_and_margin_groups(
                [
                    {
                        "product_id": (10, "Test Product"),
                        "order_id": (101, "Order 101"),
                        "qty": 2.5,
                        "price_subtotal": 100.0,
                        "total_cost": 40.0,
                    },
                    {
                        "product_id": (10, "Test Product"),
                        "order_id": (102, "Order 102"),
                        "qty": -0.5,
                        "price_subtotal": -20.0,
                        "total_cost": -8.0,
                    },
                ],
                {101: 0.5, 102: 2.0},
            )
        )
        self.assertEqual(quantity_by_product[10], 2.0)
        self.assertEqual(margin_by_product[10], 114.0)

    def test_excel_and_pdf_labels_are_explicitly_arabic(self):
        labels = self._create_wizard()._get_arabic_report_labels()
        self.assertEqual(labels["title"], "تقرير مبيعات وهوامش نقاط البيع")
        self.assertEqual(
            labels["headers"],
            [
                "اسم المنتج",
                "الكمية",
                "المجموع",
                "الخصومات",
                "المجموع بعد الخصومات",
                "الضريبة",
                "المجموع العام",
                "هامش الربح - مبلغ",
                "هامش الربح - نسبة",
            ],
        )
        self.assertEqual(labels["total"], "الإجمالي")

    def test_pdf_percentage_avoids_percent_operator_with_literal_percent(self):
        template = (
            Path(__file__).parents[1]
            / "report"
            / "pos_sales_margin_report_templates.xml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("%.2f%%", template)
        self.assertIn("'{:.2f}'.format(line['margin_percent'])", template)

from datetime import datetime
from types import SimpleNamespace

from odoo.tests.common import TransactionCase


class ReportRecords(list):
    """Small read-only record collection for refund payload regression cases."""

    def filtered(self, predicate):
        return ReportRecords(item for item in self if predicate(item))

    def sorted(self, key):
        return ReportRecords(sorted(self, key=key))

    def mapped(self, path):
        values = ReportRecords()
        for item in self:
            value = item
            for field in path.split("."):
                if not value:
                    break
                value = getattr(value, field)
            if value and value not in values:
                values.append(value)
        return values


class TestPosReportEnhancements(TransactionCase):
    def setUp(self):
        super().setUp()
        self.report = self.env["report.point_of_sale.report_saledetails"]

    def test_ranking_combines_prices_and_subtracts_refunds(self):
        def line(product_id, name, quantity, amount):
            return {
                "product_id": product_id,
                "product_name": name,
                "code": "",
                "uom": "Units",
                "quantity": quantity,
                "amount": amount,
            }

        ranked = self.report._aggregate_product_ranking(
            [
                line(1, "Burger", 5, 100),
                line(1, "Burger", 3, 45),
                line(1, "Burger", -2, -40),
                line(2, "Fries", 7, 70),
                line(3, "Return only", -1, -20),
                line(4, "Higher value tie", 6, 120),
            ]
        )
        self.assertEqual([item["product_id"] for item in ranked], [2, 4, 1, 3])
        self.assertEqual([item["rank"] for item in ranked], [1, 2, 3, 4])
        burger = ranked[2]
        self.assertEqual(burger["sold_quantity"], 8)
        self.assertEqual(burger["refund_quantity"], 2)
        self.assertEqual(burger["net_quantity"], 6)
        self.assertEqual(burger["net_amount"], 105)
        self.assertEqual(self.report._aggregate_product_ranking([]), [])

    def test_daily_details_domain_preserves_exact_bounds(self):
        domain = self.report._get_sale_details_order_domain(
            "2026-11-03 03:10:00", "2026-11-03 20:20:00", [14]
        )
        self.assertIn(("date_order", ">=", "2026-11-03 03:10:00"), domain)
        self.assertIn(("date_order", "<=", "2026-11-03 20:20:00"), domain)
        self.assertIn(("config_id", "in", [14]), domain)
        self.assertIn(("state", "in", ["paid", "invoiced", "done"]), domain)

    def test_session_details_use_session_scope_across_midnight(self):
        domain = self.report._get_sale_details_order_domain(
            "2026-11-03 00:00:00", "2026-11-03 23:59:59", [14], [58]
        )
        self.assertIn(("session_id", "in", [58]), domain)
        self.assertFalse(any(item[0] == "date_order" for item in domain))

    def test_mixed_exchange_preserves_refund_amount_and_original_invoice(self):
        currency = self.env.company.currency_id
        original_order = SimpleNamespace(
            name="POS/00080",
            pos_reference="Order 00080-001-0001",
            tracking_number="801",
            account_move=SimpleNamespace(name="INV/2026/00080"),
        )
        order = SimpleNamespace(
            _fields={"cashier": True},
            cashier="POS Employee",
            id=90,
            name="POS/00090",
            pos_reference="Order 00090-001-0001",
            tracking_number="901",
            date_order=datetime(2026, 11, 3, 9, 0),
            pricelist_id=SimpleNamespace(currency_id=currency),
            user_id=SimpleNamespace(display_name="Cashier"),
            partner_id=SimpleNamespace(display_name="Customer"),
            config_id=SimpleNamespace(display_name="POS 1"),
            session_id=SimpleNamespace(name="POS/00058"),
            account_move=False,
            payment_ids=ReportRecords(),
            amount_total=11.5,
            amount_tax=1.5,
            note="Exchange",
        )
        refund_line = SimpleNamespace(
            qty=-1,
            full_product_name="Returned Burger",
            product_id=SimpleNamespace(display_name="Burger", default_code="B1"),
            product_uom_id=SimpleNamespace(display_name="Units"),
            price_unit=20,
            discount=0,
            price_subtotal=-20,
            price_subtotal_incl=-23,
            refunded_orderline_id=SimpleNamespace(order_id=original_order),
            customer_note="Customer note",
        )
        order.lines = ReportRecords([refund_line, SimpleNamespace(qty=1)])
        detail = self.report._prepare_refund_order_details(
            ReportRecords([order]), currency
        )[0]
        self.assertEqual(detail["refund_total"], -23)
        self.assertEqual(detail["refund_subtotal"], -20)
        self.assertEqual(detail["refund_tax"], -3)
        self.assertEqual(detail["amount_total"], 11.5)
        self.assertEqual(detail["cashier"], "POS Employee")
        self.assertTrue(detail["has_sale_lines"])
        self.assertEqual(detail["original_invoices"], "INV/2026/00080")
        self.assertEqual(detail["lines"][0]["quantity"], -1)
        self.assertEqual(detail["lines"][0]["customer_note"], "Customer note")
        self.assertFalse(detail["refund_invoice"])

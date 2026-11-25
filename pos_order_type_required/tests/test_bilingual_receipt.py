from pathlib import Path

from lxml import etree

from odoo.tests.common import TransactionCase


class TestPosBilingualReceipt(TransactionCase):
    def test_product_loader_returns_both_receipt_names(self):
        product = self.env["product.product"].create({"name": "Receipt Burger"})
        session_model = self.env["pos.session"]

        english = session_model._get_pos_receipt_product_names(
            [product.id], "en_US"
        )
        arabic = session_model._get_pos_receipt_product_names(
            [product.id], "ar_001"
        )

        self.assertTrue(english[product.id])
        self.assertTrue(arabic[product.id])

    def test_receipt_template_has_bilingual_product_names(self):
        module_root = Path(__file__).parents[1]
        template_path = module_root / "static" / "src" / "app" / "order_type.xml"
        template = template_path.read_text(encoding="utf-8")

        etree.fromstring(template.encode("utf-8"))
        self.assertIn('t-inherit="point_of_sale.Orderline"', template)
        self.assertIn('t-esc="line.receiptNameAr"', template)
        self.assertIn('t-esc="line.receiptNameEn"', template)

    def test_frontend_persists_names_for_reprints(self):
        module_root = Path(__file__).parents[1]
        source = (
            module_root / "static" / "src" / "app" / "order_type.js"
        ).read_text(encoding="utf-8")

        self.assertIn("json.receipt_name_ar", source)
        self.assertIn("json.receipt_name_en", source)
        self.assertIn("receipt.orderlines = receipt.orderlines.map", source)

    def test_active_order_print_button_uses_standard_receipt_action(self):
        module_root = Path(__file__).parents[1]
        template_path = module_root / "static" / "src" / "app" / "order_type.xml"
        template = template_path.read_text(encoding="utf-8")

        etree.fromstring(template.encode("utf-8"))
        self.assertIn('t-inherit="point_of_sale.TicketScreen"', template)
        self.assertIn(
            '<ReprintReceiptButton order="_selectedSyncedOrder"/>', template
        )
        self.assertIn("load-order-button", template)

    def test_pending_order_delete_action_is_hidden(self):
        module_root = Path(__file__).parents[1]
        source = (
            module_root / "static" / "src" / "app" / "order_type.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'from "@point_of_sale/app/screens/ticket_screen/ticket_screen"',
            source,
        )
        self.assertIn("patch(TicketScreen.prototype", source)
        self.assertIn("shouldHideDeleteButton(order)", source)
        self.assertIn("if (order && !order.locked)", source)

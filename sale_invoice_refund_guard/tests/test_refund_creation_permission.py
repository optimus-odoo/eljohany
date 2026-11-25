from lxml import etree
from types import SimpleNamespace

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.refund_guard_mixin import (
    _exceeded_product_quantities,
    _is_quantity_controlled_line,
)


@tagged("post_install", "-at_install")
class TestRefundCreationPermission(TransactionCase):

    @staticmethod
    def _quantity_test_env(*products):
        products_by_id = {product.id: product for product in products}
        return {
            "product.product": SimpleNamespace(
                browse=lambda product_id: products_by_id[product_id]
            )
        }

    def test_historical_excess_for_unrelated_product_is_ignored(self):
        unrelated_product = SimpleNamespace(
            id=1,
            uom_id=SimpleNamespace(rounding=1.0),
        )
        current_product = SimpleNamespace(
            id=2,
            uom_id=SimpleNamespace(rounding=1.0),
        )
        env = self._quantity_test_env(unrelated_product, current_product)

        exceeded = _exceeded_product_quantities(
            env,
            invoiced={unrelated_product.id: 1.0, current_product.id: 10.0},
            refunded={unrelated_product.id: 2.0, current_product.id: 1.0},
            product_ids={current_product.id},
        )

        self.assertFalse(exceeded)

    def test_current_refund_product_still_uses_cumulative_quantity(self):
        current_product = SimpleNamespace(
            id=2,
            uom_id=SimpleNamespace(rounding=1.0),
        )
        env = self._quantity_test_env(current_product)

        exceeded = _exceeded_product_quantities(
            env,
            invoiced={current_product.id: 10.0},
            refunded={current_product.id: 11.0},
            product_ids={current_product.id},
        )

        self.assertEqual(
            exceeded,
            [(current_product, 11.0, 10.0)],
        )

    def test_negative_discount_line_is_not_quantity_controlled(self):
        discount_line = SimpleNamespace(
            display_type="product",
            product_id=True,
            price_subtotal=-7.44,
        )
        self.assertFalse(_is_quantity_controlled_line(discount_line))

    def test_percentage_discount_product_line_remains_quantity_controlled(self):
        product_line = SimpleNamespace(
            display_type="product",
            product_id=True,
            price_subtotal=432.56,
            discount=1.69,
        )
        self.assertTrue(_is_quantity_controlled_line(product_line))

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base_groups = "base.group_user,account.group_account_invoice"
        cls.regular_user = new_test_user(
            cls.env,
            login="refund_regular_user",
            groups=base_groups,
        )
        cls.authorized_user = new_test_user(
            cls.env,
            login="refund_authorized_user",
            groups=(
                base_groups
                + ",sale_invoice_refund_guard.group_create_customer_refund"
            ),
        )

    @staticmethod
    def _move_values(move_type):
        return {
            "move_type": move_type,
            "date": "2026-01-01",
        }

    def test_regular_user_cannot_create_customer_refund(self):
        with self.assertRaisesRegex(AccessError, "إنشاء مرتجعات العملاء"):
            self.env["account.move"].with_user(self.regular_user).create(
                self._move_values("out_refund")
            )

    def test_authorized_user_can_create_customer_refund(self):
        refund = self.env["account.move"].with_user(self.authorized_user).create(
            self._move_values("out_refund")
        )
        self.assertEqual(refund.move_type, "out_refund")

    def test_regular_user_can_still_create_customer_invoice(self):
        invoice = self.env["account.move"].with_user(self.regular_user).create(
            self._move_values("out_invoice")
        )
        self.assertEqual(invoice.move_type, "out_invoice")

    def test_regular_user_can_create_refund_from_original_invoice(self):
        invoice = self.env["account.move"].create(self._move_values("out_invoice"))
        refund_values = self._move_values("out_refund")
        refund_values["reversed_entry_id"] = invoice.id

        refund = self.env["account.move"].with_user(self.regular_user).create(
            refund_values
        )

        self.assertEqual(refund.reversed_entry_id, invoice)

    def test_context_default_is_also_protected(self):
        with self.assertRaises(AccessError):
            self.env["account.move"].with_user(self.regular_user).with_context(
                default_move_type="out_refund"
            ).create({"date": "2026-01-01"})

    def test_authorized_user_sees_create_on_customer_credit_note_list(self):
        view = self.env.ref("account.view_out_credit_note_tree")
        result = self.env["account.move"].with_user(self.authorized_user).get_view(
            view.id, "tree"
        )

        self.assertEqual(etree.fromstring(result["arch"]).get("create"), "1")

    def test_regular_user_does_not_get_create_enabled(self):
        view = self.env.ref("account.view_out_credit_note_tree")
        result = self.env["account.move"].with_user(self.regular_user).get_view(
            view.id, "tree"
        )

        self.assertNotEqual(etree.fromstring(result["arch"]).get("create"), "1")

from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestSaleCostVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sale_form = cls.env.ref("sale.view_order_form")
        cls.user_without_cost_access = new_test_user(
            cls.env,
            login="sale_cost_hidden_user",
            groups="base.group_user",
        )
        cls.user_with_cost_access = new_test_user(
            cls.env,
            login="sale_cost_visible_user",
            groups=(
                "base.group_user,"
                "product_cost_security.group_sale_order_cost_view"
            ),
        )

    def _purchase_price_nodes(self, user):
        result = self.env["sale.order"].with_user(user).get_view(
            view_id=self.sale_form.id,
            view_type="form",
        )
        return etree.fromstring(result["arch"]).xpath(
            "//field[@name='purchase_price']"
        )

    def test_cost_is_hidden_without_permission(self):
        nodes = self._purchase_price_nodes(self.user_without_cost_access)
        for node in nodes:
            if node.xpath("ancestor::tree | ancestor::list"):
                self.assertEqual(node.get("column_invisible"), "1")
            else:
                self.assertEqual(node.get("invisible"), "1")

    def test_cost_is_not_forced_hidden_with_permission(self):
        nodes = self._purchase_price_nodes(self.user_with_cost_access)
        self.assertTrue(nodes)
        for node in nodes:
            self.assertNotEqual(node.get("column_invisible"), "1")
            self.assertNotEqual(node.get("invisible"), "1")

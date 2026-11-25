from odoo.tests.common import TransactionCase


class TestEditSaleOrderSecurity(TransactionCase):
    def test_credit_limit_approval_group_is_available(self):
        group = self.env.ref(
            "edit_sale_order.group_approve_partner_credit_limit",
            raise_if_not_found=False,
        )

        self.assertTrue(group)
        self.assertEqual(group._name, "res.groups")

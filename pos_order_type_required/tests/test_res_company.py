from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestPosReceiptCompanyAlias(TransactionCase):
    def test_alias_is_required_when_option_is_enabled(self):
        company = self.env["res.company"].create({"name": "Receipt Alias Test"})

        with self.assertRaises(ValidationError):
            company.write({"pos_receipt_use_alias": True})

    def test_company_can_enable_receipt_alias(self):
        company = self.env["res.company"].create({"name": "Receipt Alias Test"})

        company.write({
            "pos_receipt_alias": "الاسم التجاري",
            "pos_receipt_use_alias": True,
        })

        self.assertTrue(company.pos_receipt_use_alias)
        self.assertEqual(company.pos_receipt_alias, "الاسم التجاري")

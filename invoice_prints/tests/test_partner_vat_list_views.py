from lxml import etree

from odoo.tests.common import TransactionCase


class TestPartnerVatListViews(TransactionCase):
    def test_partner_vat_is_available_in_all_invoice_lists(self):
        view_xmlids = (
            "account.view_out_invoice_tree",
            "account.view_out_credit_note_tree",
            "account.view_in_invoice_bill_tree",
            "account.view_in_invoice_refund_tree",
        )

        for view_xmlid in view_xmlids:
            with self.subTest(view=view_xmlid):
                view = self.env.ref(view_xmlid)
                arch = self.env["account.move"].get_view(
                    view_id=view.id,
                    view_type="tree",
                )["arch"]
                document = etree.fromstring(arch.encode())
                vat_fields = document.xpath("//field[@name='customer_vat']")
                self.assertEqual(
                    len(vat_fields),
                    1,
                    "%s must contain exactly one tax-number column" % view_xmlid,
                )
                self.assertEqual(vat_fields[0].get("optional"), "show")

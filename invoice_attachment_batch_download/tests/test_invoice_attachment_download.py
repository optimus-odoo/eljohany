# -*- coding: utf-8 -*-
import base64
import io
import zipfile

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestInvoiceAttachmentDownload(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        invoice_values = {
            "move_type": "out_invoice",
            "partner_id": cls.partner_a.id,
            "journal_id": cls.company_data["default_journal_sale"].id,
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "name": "Test line",
                        "quantity": 1,
                        "price_unit": 100,
                        "account_id": cls.company_data["default_account_revenue"].id,
                    },
                )
            ],
        }
        cls.invoice_a = cls.env["account.move"].create(invoice_values)
        cls.invoice_b = cls.env["account.move"].create(invoice_values)
        cls.misc_journal = cls.env["account.journal"].create(
            {
                "name": "Attachment Download Test Miscellaneous",
                "code": "ADTM",
                "type": "general",
                "company_id": cls.company_data["company"].id,
            }
        )
        cls.invoice_a.name = "INV/TEST/001"
        cls.invoice_b.name = "INV/TEST/002"
        cls.env["ir.attachment"].create(
            {
                "name": "invoice.pdf",
                "type": "binary",
                "datas": base64.b64encode(b"invoice-a"),
                "mimetype": "application/pdf",
                "res_model": "account.move",
                "res_id": cls.invoice_a.id,
            }
        )
        cls.env["ir.attachment"].create(
            {
                "name": "invoice.pdf",
                "type": "binary",
                "datas": base64.b64encode(b"invoice-b"),
                "mimetype": "application/pdf",
                "res_model": "account.move",
                "res_id": cls.invoice_b.id,
            }
        )

    def _wizard_from_action(self, action):
        wizard_id = int(action["url"].split("&id=")[1].split("&", 1)[0])
        return self.env["invoice.attachment.download"].browse(wizard_id)

    def test_move_lines_deduplicate_invoices(self):
        lines = self.invoice_a.line_ids | self.invoice_b.line_ids
        action = lines.action_download_invoice_attachments()
        wizard = self._wizard_from_action(action)

        self.assertEqual(wizard.invoice_count, 2)
        self.assertEqual(wizard.attachment_count, 2)
        with zipfile.ZipFile(
            io.BytesIO(base64.b64decode(wizard.file_data)), "r"
        ) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 2)
            self.assertEqual(len({name.split("/", 1)[0] for name in names}), 2)

    def test_non_invoice_selection_is_rejected(self):
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.misc_journal.id,
            }
        )
        with self.assertRaises(UserError):
            entry.action_download_invoice_attachments()

    def test_invoice_without_attachments_is_rejected(self):
        invoice = self.invoice_a.copy()
        with self.assertRaises(UserError):
            invoice.action_download_invoice_attachments()

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestPartnerDualAccountControl(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_dual_account_control_enabled = True
        cls.company_data_2["company"].partner_dual_account_control_enabled = True
        cls.receivable_account = cls.company_data["default_account_receivable"]
        cls.payable_account = cls.company_data["default_account_payable"]
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Dual Role Partner",
                "customer_rank": 1,
                "supplier_rank": 1,
                "property_account_receivable_id": cls.receivable_account.id,
                "property_account_payable_id": cls.payable_account.id,
            }
        )
        cls.partner.with_company(cls.company_data_2["company"]).write(
            {
                "property_account_receivable_id": cls.company_data_2[
                    "default_account_receivable"
                ].id,
                "property_account_payable_id": cls.company_data_2[
                    "default_account_payable"
                ].id,
            }
        )

    def _create_invoice(self, move_type, company_data=None, fiscal_position=None):
        company_data = company_data or self.company_data
        company = company_data["company"]
        account = (
            company_data["default_account_revenue"]
            if move_type.startswith("out_")
            else company_data["default_account_expense"]
        )
        journal = (
            company_data["default_journal_sale"]
            if move_type.startswith("out_")
            else company_data["default_journal_purchase"]
        )
        return self.env["account.move"].with_company(company).create(
            {
                "move_type": move_type,
                "company_id": company.id,
                "journal_id": journal.id,
                "partner_id": self.partner.id,
                "invoice_date": fields.Date.today(),
                "fiscal_position_id": fiscal_position.id
                if fiscal_position
                else False,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Directional account test",
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": account.id,
                        }
                    )
                ],
            }
        )

    def test_customer_and_vendor_documents_use_separate_accounts(self):
        for move_type, expected_account in (
            ("out_invoice", self.receivable_account),
            ("out_refund", self.receivable_account),
            ("in_invoice", self.payable_account),
            ("in_refund", self.payable_account),
            ("out_receipt", self.receivable_account),
            ("in_receipt", self.payable_account),
        ):
            document = self._create_invoice(move_type)
            self.assertEqual(
                document.expected_partner_account_id,
                expected_account,
            )
            self.assertEqual(
                document.line_ids.filtered(
                    lambda line: line.display_type == "payment_term"
                ).account_id,
                expected_account,
            )

    def test_documents_use_company_specific_partner_accounts(self):
        second_company = self.company_data_2["company"]
        second_receivable = self.company_data_2["default_account_receivable"]
        second_payable = self.company_data_2["default_account_payable"]

        customer_invoice = self._create_invoice(
            "out_invoice",
            company_data=self.company_data_2,
        )
        vendor_bill = self._create_invoice(
            "in_invoice",
            company_data=self.company_data_2,
        )

        self.assertEqual(customer_invoice.company_id, second_company)
        self.assertEqual(
            customer_invoice.expected_partner_account_id,
            second_receivable,
        )
        self.assertEqual(vendor_bill.expected_partner_account_id, second_payable)
        self.assertNotEqual(second_receivable, self.receivable_account)
        self.assertNotEqual(second_payable, self.payable_account)

    def test_fiscal_position_mapping_is_part_of_expected_account(self):
        mapped_receivable = self.receivable_account.copy(
            {
                "name": "Mapped Receivable Test Account",
                "code": "TREC-MAPPED",
            }
        )
        fiscal_position = self.env["account.fiscal.position"].create(
            {
                "name": "Settlement Account Mapping Test",
                "company_id": self.env.company.id,
                "account_ids": [
                    Command.create(
                        {
                            "account_src_id": self.receivable_account.id,
                            "account_dest_id": mapped_receivable.id,
                        }
                    )
                ],
            }
        )
        invoice = self._create_invoice(
            "out_invoice",
            fiscal_position=fiscal_position,
        )

        self.assertEqual(invoice.expected_partner_account_id, mapped_receivable)
        self.assertEqual(
            invoice.line_ids.filtered(
                lambda line: line.display_type == "payment_term"
            ).account_id,
            mapped_receivable,
        )

    def test_posting_rejects_another_receivable_account(self):
        invoice = self._create_invoice("out_invoice")
        other_receivable = self.receivable_account.copy(
            {
                "name": "Other Receivable Test Account",
                "code": "TREC-DUAL",
            }
        )
        invoice.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        ).account_id = other_receivable

        with self.assertRaises(ValidationError):
            invoice.action_post()

    def test_disabled_company_control_does_not_block_existing_drafts(self):
        invoice = self._create_invoice("out_invoice")
        other_receivable = self.receivable_account.copy(
            {
                "name": "Legacy Receivable Test Account",
                "code": "TREC-LEGACY",
            }
        )
        invoice.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        ).account_id = other_receivable
        self.env.company.partner_dual_account_control_enabled = False

        invoice._validate_partner_account_control()

    def test_payment_rejects_wrong_directional_account(self):
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "amount": 100.0,
                "date": fields.Date.today(),
                "currency_id": self.env.company.currency_id.id,
                "journal_id": self.company_data["default_journal_bank"].id,
            }
        )
        payment.destination_account_id = self.payable_account

        self.assertEqual(payment.destination_account_control_state, "invalid")
        with self.assertRaises(ValidationError):
            payment._validate_directional_destination_account()

    def test_payment_reports_another_receivable_as_mismatch(self):
        other_receivable = self.receivable_account.copy(
            {
                "name": "Unrelated Receivable Payment Account",
                "code": "TREC-PAYMENT",
            }
        )
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "amount": 100.0,
                "date": fields.Date.today(),
                "currency_id": self.env.company.currency_id.id,
                "journal_id": self.company_data["default_journal_bank"].id,
                "destination_account_id": other_receivable.id,
            }
        )

        self.assertEqual(payment.destination_account_control_state, "mismatch")
        with self.assertRaises(ValidationError):
            payment._validate_directional_destination_account()

    def test_customer_and_supplier_payments_use_separate_accounts(self):
        for payment_type, partner_type, expected_account in (
            ("inbound", "customer", self.receivable_account),
            ("outbound", "supplier", self.payable_account),
        ):
            payment = self.env["account.payment"].create(
                {
                    "payment_type": payment_type,
                    "partner_type": partner_type,
                    "partner_id": self.partner.id,
                    "amount": 100.0,
                    "date": fields.Date.today(),
                    "currency_id": self.env.company.currency_id.id,
                    "journal_id": self.company_data["default_journal_bank"].id,
                }
            )
            self.assertEqual(payment.destination_account_id, expected_account)
            self.assertEqual(
                payment.expected_destination_account_id,
                expected_account,
            )
            self.assertEqual(payment.destination_account_control_state, "valid")
            payment._validate_directional_destination_account()

    def test_payment_can_settle_open_invoice_after_partner_account_change(self):
        invoice = self._create_invoice("out_invoice")
        invoice.action_post()
        former_receivable = self.receivable_account
        new_receivable = self.receivable_account.copy(
            {
                "name": "New Receivable Test Account",
                "code": "TREC-NEW",
            }
        )
        self.partner.property_account_receivable_id = new_receivable

        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "amount": 100.0,
                "date": fields.Date.today(),
                "currency_id": self.env.company.currency_id.id,
                "journal_id": self.company_data["default_journal_bank"].id,
            }
        )
        payment.destination_account_id = former_receivable

        self.assertEqual(
            payment.destination_account_control_state,
            "open_document",
        )
        payment._validate_directional_destination_account()

    def test_audit_reports_deprecated_partner_account(self):
        dedicated_payable = self.payable_account.copy(
            {
                "name": "Deprecated Payable Test Account",
                "code": "TPAY-DUAL",
            }
        )
        self.partner.property_account_payable_id = dedicated_payable
        dedicated_payable.deprecated = True

        wizard = self.env["partner.account.audit.wizard"].create(
            {
                "company_id": self.env.company.id,
                "partner_ids": [Command.set(self.partner.ids)],
            }
        )
        wizard.action_run_audit()

        self.assertIn(
            "deprecated",
            wizard.line_ids.mapped("issue_type"),
        )

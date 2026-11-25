from datetime import date
from pathlib import Path

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestVendorLedgerReport(TransactionCase):
    def _create_wizard(self, **values):
        defaults = {
            "company_id": self.env.company.id,
            "show_all_suppliers": True,
            "date_from": date(2026, 10, 1),
            "date_to": date(2026, 10, 31),
        }
        defaults.update(values)
        return self.env["vendor.ledger.report.wizard"].create(defaults)

    def test_invalid_date_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_wizard(
                date_from=date(2026, 11, 1),
                date_to=date(2026, 10, 31),
            )

    def test_supplier_is_required_unless_show_all_is_enabled(self):
        wizard = self._create_wizard(show_all_suppliers=False)
        with self.assertRaises(UserError):
            wizard._validate_report_options()

    def test_detailed_display_is_selected_by_default(self):
        self.assertEqual(self._create_wizard().display_mode, "details")

    def test_folded_mode_keeps_opening_period_and_closing_totals(self):
        wizard = self._create_wizard(display_mode="summary")
        partner = self.env["res.partner"].create(
            {"name": "Summary Supplier", "supplier_rank": 1}
        )
        report = wizard._build_partner_report(
            partner,
            {"debit": 100.0, "credit": 20.0},
            period_values={"debit": 30.0, "credit": 50.0},
        )
        self.assertEqual(report["opening_balance"], 80.0)
        self.assertEqual(report["period_debit"], 30.0)
        self.assertEqual(report["period_credit"], 50.0)
        self.assertEqual(report["closing_balance"], 60.0)
        self.assertFalse(report["lines"])

    def test_domain_is_not_restricted_to_payable_accounts(self):
        wizard = self._create_wizard()
        partner = self.env["res.partner"].create(
            {"name": "Domain Supplier", "supplier_rank": 1}
        )
        domain = wizard._get_base_line_domain(partner)
        domain_text = repr(domain)
        self.assertNotIn("account_type", domain_text)
        self.assertNotIn("liability_payable", domain_text)
        self.assertIn(("parent_state", "=", "posted"), domain)

    def test_show_all_returns_unique_commercial_suppliers(self):
        commercial = self.env["res.partner"].create(
            {"name": "Commercial Supplier", "supplier_rank": 1}
        )
        self.env["res.partner"].create(
            {
                "name": "Supplier Contact",
                "parent_id": commercial.id,
                "supplier_rank": 1,
            }
        )
        targets = self._create_wizard()._get_target_partners()
        self.assertIn(commercial, targets)
        self.assertEqual(targets.filtered(lambda item: item == commercial), commercial)

    def test_pdf_template_uses_odoo_html_container(self):
        template = (
            Path(__file__).parents[1]
            / "report"
            / "vendor_ledger_report_templates.xml"
        ).read_text(encoding="utf-8")
        self.assertIn('t-call="web.html_container"', template)
        self.assertIn("doc.display_mode == 'details'", template)

    def test_html_preview_action_and_button_are_declared(self):
        addon_root = Path(__file__).parents[1]
        actions = (
            addon_root / "report" / "vendor_ledger_report_actions.xml"
        ).read_text(encoding="utf-8")
        wizard_view = (
            addon_root / "views" / "vendor_ledger_report_views.xml"
        ).read_text(encoding="utf-8")
        wizard_source = (
            addon_root / "models" / "vendor_ledger_report_wizard.py"
        ).read_text(encoding="utf-8")

        self.assertIn('id="action_vendor_ledger_report_html"', actions)
        self.assertIn('<field name="report_type">qweb-html</field>', actions)
        self.assertIn('name="action_view_report"', wizard_view)
        self.assertIn("def action_view_report(", wizard_source)
        self.assertIn(
            '"vendor_ledger_report.action_vendor_ledger_report_html"',
            wizard_source,
        )

    def test_excel_uses_supported_print_area_api(self):
        wizard_source = (
            Path(__file__).parents[1]
            / "models"
            / "vendor_ledger_report_wizard.py"
        ).read_text(encoding="utf-8")
        self.assertIn("worksheet.print_area(", wizard_source)
        self.assertNotIn("worksheet.set_print_area(", wizard_source)

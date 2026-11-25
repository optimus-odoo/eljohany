import ast
from datetime import datetime
from pathlib import Path

from lxml import etree

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestPosShiftSummaryReport(TransactionCase):
    def _create_wizard(self, **values):
        defaults = {
            "company_id": self.env.company.id,
            "date_from": datetime(2026, 10, 21, 5, 30, 0),
            "date_to": datetime(2026, 10, 21, 18, 45, 0),
        }
        defaults.update(values)
        return self.env["pos.shift.summary.report.wizard"].create(defaults)

    def test_invalid_date_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_wizard(
                date_from=datetime(2026, 10, 21, 19, 0, 0),
                date_to=datetime(2026, 10, 21, 18, 0, 0),
            )

    def test_at_least_one_pos_is_required_server_side(self):
        with self.assertRaises(UserError):
            self._create_wizard()._validate_report_options()

    def test_exact_inclusive_datetime_domains(self):
        wizard = self._create_wizard()
        self.assertIn(
            ("date_order", ">=", "2026-10-21 05:30:00"),
            wizard._get_order_domain(),
        )
        self.assertIn(
            ("date_order", "<=", "2026-10-21 18:45:00"),
            wizard._get_order_domain(),
        )
        self.assertIn(
            ("start_at", "<=", "2026-10-21 18:45:00"),
            wizard._get_session_domain(),
        )
        self.assertIn(
            ("stop_at", ">=", "2026-10-21 05:30:00"),
            wizard._get_session_domain(),
        )

    def test_automatic_report_domains_are_limited_to_one_session(self):
        wizard = self.env["pos.shift.summary.report.wizard"].new(
            {
                "company_id": self.env.company.id,
                "pos_config_ids": [(6, 0, [24])],
                "session_ids": [(6, 0, [42])],
                "date_from": datetime(2026, 10, 23, 10, 30, 0),
                "date_to": datetime(2026, 10, 24, 2, 16, 57),
            }
        )
        self.assertIn(("session_id", "in", [42]), wizard._get_order_domain())
        self.assertIn(("id", "in", [42]), wizard._get_session_domain())

    def test_signed_amounts_separate_sales_and_refunds(self):
        wizard = self._create_wizard()
        values = wizard._split_signed_amounts(
            [100.0, 25.0, -20.0, -5.0]
        )
        self.assertEqual(values["positive"], 125.0)
        self.assertEqual(values["negative"], 25.0)
        self.assertEqual(values["net"], 100.0)

        sales = wizard._build_sales_totals([900.0, -50.0], 100.0)
        self.assertEqual(sales["gross_sales"], 1000.0)
        self.assertEqual(sales["refunds"], 50.0)
        self.assertEqual(sales["discounts"], 100.0)
        self.assertEqual(sales["net_sales"], 850.0)

    def test_local_datetime_is_printed_in_user_timezone(self):
        wizard = self._create_wizard().with_context(tz="Asia/Riyadh")
        self.assertEqual(
            wizard._format_report_datetime(wizard.date_from),
            "2026-10-21 08:30:00",
        )
        self.assertEqual(
            wizard._get_report_filename(),
            "POS_Shift_20261021_083000_20261021_214500",
        )

        session = self.env["pos.session"].new(
            {
                "start_at": datetime(2026, 10, 23, 10, 30, 0),
                "stop_at": datetime(2026, 10, 24, 2, 16, 57),
            }
        ).with_context(tz="Asia/Riyadh")
        self.assertEqual(
            session._get_closing_shift_report_filename(),
            "POS_Shift_20261023_133000_20261024_051657",
        )

    def test_thermal_template_is_standalone_and_valid_xml(self):
        module_root = Path(__file__).parents[1]
        template_path = module_root / "report" / "pos_shift_summary_report_templates.xml"
        action_path = module_root / "report" / "pos_shift_summary_report_actions.xml"
        template = template_path.read_text(encoding="utf-8")
        action = action_path.read_text(encoding="utf-8")
        etree.fromstring(template.encode("utf-8"))
        etree.fromstring(action.encode("utf-8"))
        self.assertIn('t-call="web.html_container"', template)
        self.assertIn('class="article"', template)
        self.assertIn('t-att-data-oe-lang="lang"', template)
        self.assertNotIn('t-call="web.external_layout"', template)
        self.assertIn('<field name="page_width">80</field>', action)
        self.assertIn("تقرير المناوبة", template)

    def test_report_context_forces_arabic_utf8_layout(self):
        source = (
            Path(__file__).parents[1]
            / "report"
            / "pos_shift_summary_report.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"lang": "ar_001"', source)

    def test_report_action_skips_unrelated_document_layout_setup(self):
        source = (
            Path(__file__).parents[1]
            / "models"
            / "pos_shift_summary_report_wizard.py"
        ).read_text(encoding="utf-8")
        self.assertIn("config=False", source)
        self.assertNotIn("cash_move.counterpart_account_id", source)

    def test_closing_popup_has_independent_shift_report_button(self):
        module_root = Path(__file__).parents[1]
        manifest = ast.literal_eval(
            (module_root / "__manifest__.py").read_text(encoding="utf-8")
        )
        asset_paths = manifest["assets"]["point_of_sale._assets_pos"]
        self.assertIn(
            "pos_shift_summary_report/static/src/app/closing_shift_report.js",
            asset_paths,
        )
        self.assertIn(
            "pos_shift_summary_report/static/src/app/closing_shift_report.xml",
            asset_paths,
        )

        source = (
            module_root / "static" / "src" / "app" / "closing_shift_report.js"
        ).read_text(encoding="utf-8")
        popup_template = (
            module_root / "static" / "src" / "app" / "closing_shift_report.xml"
        ).read_text(encoding="utf-8")
        etree.fromstring(popup_template.encode("utf-8"))
        self.assertIn("async downloadShiftReport()", source)
        self.assertIn("await this.report.doAction", source)
        self.assertNotIn("async closeSession()", source)
        self.assertNotIn("redirectToBackend", source)
        self.assertNotIn("this.orm", source)
        self.assertIn('t-inherit="point_of_sale.ClosePosPopup"', popup_template)
        self.assertIn('t-on-click="downloadShiftReport"', popup_template)
        self.assertIn("Shift Report", popup_template)

        report_source = (
            module_root / "report" / "pos_shift_summary_report.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "report_end = sessions.stop_at or fields.Datetime.now()",
            report_source,
        )
        self.assertNotIn('sessions.state != "closed"', report_source)

        report_action = (
            module_root / "report" / "pos_shift_summary_report_actions.xml"
        ).read_text(encoding="utf-8")
        report_template = (
            module_root / "report" / "pos_shift_summary_report_templates.xml"
        ).read_text(encoding="utf-8")
        self.assertIn("action_pos_session_shift_summary_report_pdf", report_action)
        self.assertIn('template id="session_shift"', report_template)

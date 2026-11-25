from odoo import fields
from odoo.tests.common import TransactionCase


class TestExtendedExecutiveDashboards(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_provider_registers_all_extended_dashboard_codes(self):
        codes = self.env[
            "executive.intelligence.service"
        ]._ei_supported_dashboard_codes()
        self.assertTrue(
            {
                "executive",
                "finance",
                "sales",
                "product",
                "forecast",
                "hr",
                "operations",
                "risk",
            }.issubset(codes)
        )

    def test_accounting_user_receives_only_relevant_extended_dashboard(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Automatic Finance Intelligence User",
                "login": "automatic.finance.intelligence.user",
                "email": "automatic.finance.intelligence.user@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, self.company.ids)],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("account.group_account_user").id,
                        ],
                    )
                ],
            }
        )

        self.env["res.users"]._ei_setup_extended_defaults()

        codes = set(user.ei_dashboard_ids.mapped("code"))
        self.assertIn("finance", codes)
        self.assertNotIn("hr", codes)
        self.assertNotIn("operations", codes)
        self.assertEqual(user.ei_financial_access, "summary")
        self.assertEqual(user.ei_hr_access, "none")

    def test_administrator_receives_every_available_dashboard(self):
        self.env["res.users"]._ei_setup_extended_defaults()
        administrator = self.env.ref("base.user_admin")
        supported = self.env[
            "executive.intelligence.service"
        ]._ei_supported_dashboard_codes()
        assigned = set(administrator.ei_dashboard_ids.mapped("code"))

        self.assertTrue(supported.issubset(assigned))
        self.assertEqual(administrator.ei_financial_access, "detail")
        self.assertEqual(administrator.ei_hr_access, "payroll")
        self.assertTrue(administrator.ei_can_forecast)
        self.assertTrue(administrator.ei_can_manage_alerts)
        bootstrap = self.env["executive.intelligence.service"].with_user(
            administrator
        ).get_bootstrap()
        visible = {dashboard["code"] for dashboard in bootstrap["dashboards"]}
        self.assertTrue(supported.issubset(visible))

    def test_finance_and_hr_providers_return_verified_structures(self):
        filters = {
            "company_ids": self.company.ids,
            "date_from": fields.Date.today(),
            "date_to": fields.Date.today(),
        }
        service = self.env["executive.intelligence.service"].with_user(
            self.env.ref("base.user_admin")
        )

        finance = service._ei_finance_dashboard(filters)
        hr = service._ei_hr_dashboard(filters)

        self.assertIn("period_result", finance["definitions"])
        self.assertEqual(finance["tables"][0]["key"], "finance_by_company")
        self.assertEqual(hr["tables"][0]["key"], "employees_by_department")
        self.assertEqual(
            {chart["type"] for chart in finance["charts"]}, {"bar", "gauge"}
        )
        self.assertEqual(hr["charts"][0]["type"], "column")

    def test_generated_profiles_exist_for_each_major_role(self):
        self.env["res.users"]._ei_setup_extended_defaults()
        expected = {
            f"extended_finance_viewer_company_{self.company.id}",
            f"extended_sales_manager_company_{self.company.id}",
            f"extended_hr_manager_company_{self.company.id}",
            f"extended_operations_manager_company_{self.company.id}",
            f"extended_executive_manager_company_{self.company.id}",
        }
        profiles = self.env["executive.intelligence.access.profile"].search(
            [("auto_code", "in", list(expected))]
        )
        self.assertEqual(set(profiles.mapped("auto_code")), expected)


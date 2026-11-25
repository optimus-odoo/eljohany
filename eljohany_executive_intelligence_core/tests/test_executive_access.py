from odoo.exceptions import AccessError, UserError
from odoo.modules.module import get_module_resource
from odoo.tests.common import TransactionCase
from odoo.tools.translate import TranslationFileReader


class TestExecutiveIntelligenceAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.access_group = cls.env.ref(
            "eljohany_executive_intelligence_core.group_ei_user"
        )
        cls.risk_dashboard = cls.env.ref(
            "eljohany_executive_intelligence_core.dashboard_risk"
        )
        cls.finance_dashboard = cls.env.ref(
            "eljohany_executive_intelligence_core.dashboard_finance"
        )
        cls.profile = cls.env["executive.intelligence.access.profile"].create(
            {
                "name": "Risk Viewer",
                "dashboard_ids": [(6, 0, cls.risk_dashboard.ids)],
                "company_ids": [(6, 0, cls.env.company.ids)],
            }
        )
        cls.viewer = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Executive Intelligence Viewer",
                "login": "ei.viewer",
                "email": "ei.viewer@example.com",
                "company_id": cls.env.company.id,
                "company_ids": [(6, 0, cls.env.company.ids)],
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id, cls.access_group.id])],
                "ei_access_profile_id": cls.profile.id,
            }
        )
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Executive Intelligence Outsider",
                "login": "ei.outsider",
                "email": "ei.outsider@example.com",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def test_unauthorized_user_cannot_bootstrap(self):
        service = self.env["executive.intelligence.service"].with_user(self.outsider)
        with self.assertRaises(AccessError):
            service.get_bootstrap()

    def test_dashboard_without_provider_is_hidden(self):
        self.env[
            "executive.intelligence.dashboard"
        ]._ei_sync_provider_availability()
        bootstrap = self.env["executive.intelligence.service"].with_user(
            self.viewer
        ).get_bootstrap()
        self.assertEqual(bootstrap["dashboards"], [])
        self.assertFalse(self.risk_dashboard.active)

    def test_direct_call_to_unassigned_dashboard_is_blocked(self):
        service = self.env["executive.intelligence.service"].with_user(self.viewer)
        with self.assertRaises(AccessError):
            service.get_dashboard_data(
                "finance", {"company_ids": self.env.company.ids}
            )

    def test_custom_company_outside_scope_is_blocked(self):
        other_company = self.env["res.company"].create({"name": "Outside Scope"})
        service = self.env["executive.intelligence.service"].with_user(self.viewer)
        with self.assertRaises(AccessError):
            service.get_dashboard_data(
                "risk", {"company_ids": [other_company.id]}
            )

    def test_empty_company_filter_does_not_broaden_scope(self):
        service = self.env["executive.intelligence.service"].with_user(self.viewer)
        with self.assertRaises(AccessError):
            service.get_dashboard_data("risk", {"company_ids": []})

    def test_access_change_is_audited_and_log_is_immutable(self):
        self.viewer.write({"ei_custom_access": True})
        log = self.env["executive.intelligence.access.log"].sudo().search(
            [("target_user_id", "=", self.viewer.id)],
            order="id desc",
            limit=1,
        )
        self.assertTrue(log)
        self.assertEqual(log.operation, "write")
        with self.assertRaises(AccessError):
            log.unlink()

    def test_arabic_translation_is_odoo_loadable(self):
        path = get_module_resource(
            "eljohany_executive_intelligence_core", "i18n", "ar_001.po"
        )
        rows = list(TranslationFileReader(path))
        self.assertGreaterEqual(len(rows), 101)
        translations = {row["src"]: row["value"] for row in rows}
        self.assertEqual(
            translations["Executive Intelligence Center"],
            "مركز المعلومات والذكاء التنفيذي",
        )
        self.assertEqual(translations["Companies"], "الشركات")
        self.assertEqual(translations["Apply"], "تطبيق")

    def test_administrator_is_configured_automatically(self):
        self.env["res.users"]._ei_setup_core_defaults()
        administrator = self.env.ref("base.user_admin")
        self.assertTrue(administrator.ei_enabled)
        self.assertTrue(administrator.ei_custom_access)
        self.assertTrue(administrator.ei_auto_configured)
        self.assertEqual(administrator.ei_financial_access, "detail")
        self.assertEqual(administrator.ei_hr_access, "payroll")
        self.assertEqual(administrator.ei_company_ids, administrator.company_ids)

    def test_visual_payload_contract_accepts_supported_chart_types(self):
        service = self.env["executive.intelligence.service"]
        charts = []
        for chart_type in service._EI_CHART_TYPES:
            item = {"key": chart_type, "label": chart_type, "value": 1.0}
            if chart_type == "geo":
                item.update({"latitude": 24.7136, "longitude": 46.6753})
            charts.append(
                {
                    "key": chart_type,
                    "title": chart_type,
                    "type": chart_type,
                    "items": [item],
                }
            )

        payload = service._ei_validate_visual_payload({"charts": charts})

        self.assertEqual(len(payload["charts"]), len(service._EI_CHART_TYPES))
        self.assertEqual(payload["cards"], [])
        self.assertEqual(payload["tables"], [])

    def test_visual_payload_rejects_non_finite_and_invalid_geo_values(self):
        service = self.env["executive.intelligence.service"]
        with self.assertRaises(UserError):
            service._ei_validate_visual_payload(
                {
                    "charts": [
                        {
                            "key": "invalid",
                            "title": "Invalid",
                            "type": "bar",
                            "items": [{"key": 1, "value": float("nan")}],
                        }
                    ]
                }
            )
        with self.assertRaises(UserError):
            service._ei_validate_visual_payload(
                {
                    "charts": [
                        {
                            "key": "invalid_geo",
                            "title": "Invalid Geo",
                            "type": "geo",
                            "items": [
                                {
                                    "key": 1,
                                    "value": 1.0,
                                    "latitude": 120.0,
                                    "longitude": 46.0,
                                }
                            ],
                        }
                    ]
                }
            )

    def test_period_comparison_preserves_source_values(self):
        comparison = self.env[
            "executive.intelligence.service"
        ]._ei_period_comparison(120, 100)
        self.assertEqual(comparison["display"], "+20.0%")
        self.assertEqual(comparison["direction"], "up")
        self.assertEqual(comparison["tone"], "success")
        self.assertEqual(comparison["current"], 120.0)
        self.assertEqual(comparison["previous"], 100.0)


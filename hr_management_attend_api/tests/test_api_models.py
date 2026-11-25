from datetime import timedelta
from unittest.mock import Mock, patch

import requests as http_requests
from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from ..models.attendance_service import AttendanceAPIError


@tagged("post_install", "-at_install")
class TestHrManagementAttendanceApi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.branch = cls.env["res.branch"].create(
            {
                "name": "API Test Branch",
                "company_id": cls.company.id,
                "api_attendance_enabled": True,
                "api_latitude": 24.7136,
                "api_longitude": 46.6753,
                "api_radius_m": 250,
                "api_max_accuracy_m": 50,
                "api_timezone": "Asia/Riyadh",
                "api_external_id": "external-branch-1",
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "API Test Employee",
                "company_id": cls.company.id,
                "api_branch_id": cls.branch.id,
                "api_employee_number": "API-TEST-001",
                "api_external_id": "external-employee-1",
                "api_access_enabled": True,
                "work_email": "api.test@example.com",
            }
        )

    def test_password_hash_and_token_lifecycle(self):
        credential_model = self.env["hr.attendance.api.credential"]
        credential = credential_model.create(
            {
                "employee_id": self.employee.id,
                "login": "Employee.Test@Example.com",
                "password_hash": credential_model._hash_password("strong-pass-123"),
            }
        )
        self.assertEqual(credential.login, "employee.test@example.com")
        self.assertTrue(credential._verify_password("strong-pass-123"))
        self.assertFalse(credential._verify_password("incorrect-password"))

        token, raw_token = self.env["hr.attendance.api.token"]._issue(
            "employee", self.company, employee=self.employee, lifetime_hours=1
        )
        authenticated = self.env["hr.attendance.api.token"]._authenticate_bearer(
            "Bearer %s" % raw_token
        )
        self.assertEqual(authenticated, token)
        self.assertNotEqual(token.token_digest, raw_token)
        token._revoke()
        self.assertFalse(
            self.env["hr.attendance.api.token"]._authenticate_bearer(
                "Bearer %s" % raw_token
            )
        )

    def test_check_in_out_and_idempotent_replay(self):
        service = self.env["hr.attendance.api.service"]
        check_in_payload = {
            "latitude": 24.7136,
            "longitude": 46.6753,
            "accuracy": 10,
            "shift": "morning",
        }
        attendance, replayed = service._check_in(
            self.employee,
            check_in_payload,
            idempotency_key="test-check-in-1",
            source_ip="127.0.0.1",
            request_id="request-check-in-1",
        )
        self.assertFalse(replayed)
        self.assertFalse(attendance.check_out)
        self.assertEqual(attendance.api_branch_id, self.branch)

        replay_attendance, replayed = service._check_in(
            self.employee,
            check_in_payload,
            idempotency_key="test-check-in-1",
            source_ip="127.0.0.1",
        )
        self.assertTrue(replayed)
        self.assertEqual(replay_attendance, attendance)

        attendance.write({"check_in": fields.Datetime.now() - timedelta(minutes=1)})
        attendance, replayed = service._check_out(
            self.employee,
            {
                "latitude": 24.7136,
                "longitude": 46.6753,
                "accuracy": 10,
                "shift": "evening",
            },
            idempotency_key="test-check-out-1",
            source_ip="127.0.0.1",
            request_id="request-check-out-1",
        )
        self.assertFalse(replayed)
        self.assertTrue(attendance.check_out)
        self.assertEqual(len(attendance.api_event_ids), 2)
        self.assertEqual(
            set(attendance.api_event_ids.mapped("request_id")),
            {"request-check-in-1", "request-check-out-1"},
        )

    def test_reject_outside_radius(self):
        service = self.env["hr.attendance.api.service"]
        with self.assertRaises(AttendanceAPIError) as raised:
            service._check_in(
                self.employee,
                {
                    "latitude": 25.0000,
                    "longitude": 47.0000,
                    "accuracy": 10,
                    "shift": "morning",
                },
            )
        self.assertEqual(raised.exception.code, "outside_branch_radius")

    def test_reject_non_finite_gps_value(self):
        with self.assertRaises(AttendanceAPIError) as raised:
            self.env["hr.attendance.api.service"]._check_in(
                self.employee,
                {
                    "latitude": float("nan"),
                    "longitude": 46.6753,
                    "accuracy": 10,
                    "shift": "morning",
                },
            )
        self.assertEqual(raised.exception.details, {"latitude": "invalid_number"})

    def test_external_sync_creates_then_updates_attendance(self):
        service = self.env["hr.attendance.api.sync.service"]
        config = {"company": self.company, "timezone": "Asia/Riyadh"}
        row = {
            "id": "external-attendance-1",
            "employee_id": "must-not-be-used-for-employee-matching",
            "employee_number": "API-TEST-001",
            "branch_id": "external-branch-1",
            "check_in": "2026-08-13T08:00:00+03:00",
            "shift": "morning",
            "latitude": 24.7136,
            "longitude": 46.6753,
            "accuracy": 10,
        }
        state, message = service._import_attendance_row(row, config)
        self.assertEqual(state, "created")
        self.assertFalse(message)
        attendance = self.env["hr.attendance"].search(
            [("api_external_id", "=", "external-attendance-1")]
        )
        self.assertEqual(attendance.api_source, "external_sync")
        self.assertFalse(attendance.check_out)

        row["check_out"] = "2026-08-13T17:00:00+03:00"
        row["check_out_latitude"] = 24.7136
        row["check_out_longitude"] = 46.6753
        state, message = service._import_attendance_row(row, config)
        self.assertEqual(state, "updated")
        self.assertFalse(message)
        self.assertTrue(attendance.check_out)
        self.assertEqual(len(attendance.api_event_ids), 2)
        self.assertEqual(
            self.env["hr.attendance"].search_count(
                [("api_external_id", "=", "external-attendance-1")]
            ),
            1,
        )

    def test_external_sync_matches_employee_number_across_companies(self):
        other_company = self.env["res.company"].create({"name": "Other API Company"})
        employee = self.env[
            "hr.attendance.api.sync.service"
        ]._employee_for_row(
            {"employee_number": "API-TEST-001"},
            other_company,
        )
        self.assertEqual(employee, self.employee)

    def test_external_sync_combines_hr2_attendance_date_and_times(self):
        state, message = self.env[
            "hr.attendance.api.sync.service"
        ]._import_attendance_row(
            {
                "id": "external-attendance-split-time",
                "employee_number": "API-TEST-001",
                "attendance_date": "2026-08-15",
                "check_in_time": "08:44:40",
                "check_out_time": "12:57:10",
            },
            {"company": self.company, "timezone": "Asia/Riyadh"},
        )
        self.assertEqual(state, "created")
        self.assertFalse(message)
        attendance = self.env["hr.attendance"].search(
            [("api_external_id", "=", "external-attendance-split-time")]
        )
        self.assertEqual(
            attendance.check_in,
            fields.Datetime.to_datetime("2026-08-15 05:44:40"),
        )
        self.assertEqual(
            attendance.check_out,
            fields.Datetime.to_datetime("2026-08-15 09:57:10"),
        )

    def test_external_sync_uses_requested_day_for_time_only_rows(self):
        state, message = self.env[
            "hr.attendance.api.sync.service"
        ]._import_attendance_row(
            {
                "id": "external-attendance-time-only",
                "employee_number": "API-TEST-001",
                "check_in_time": "07:30:00",
            },
            {
                "company": self.company,
                "timezone": "Asia/Riyadh",
                "pull_date": "2026-08-16",
            },
        )
        self.assertEqual(state, "created")
        self.assertFalse(message)
        attendance = self.env["hr.attendance"].search(
            [("api_external_id", "=", "external-attendance-time-only")]
        )
        self.assertEqual(
            attendance.check_in,
            fields.Datetime.to_datetime("2026-08-16 04:30:00"),
        )

    def test_external_sync_imports_without_branch_mapping(self):
        employee = self.env["hr.employee"].create(
            {
                "name": "API Employee Without Branch",
                "company_id": self.company.id,
                "api_employee_number": "API-TEST-002",
            }
        )
        state, message = self.env[
            "hr.attendance.api.sync.service"
        ]._import_attendance_row(
            {
                "id": "external-attendance-without-branch",
                "employee_number": "API-TEST-002",
                "branch_id": "unmapped-branch",
                "check_in": "2026-08-14T08:00:00+03:00",
            },
            {"company": self.company, "timezone": "Asia/Riyadh"},
        )
        self.assertEqual(state, "created")
        self.assertFalse(message)
        attendance = self.env["hr.attendance"].search(
            [("api_external_id", "=", "external-attendance-without-branch")]
        )
        self.assertEqual(attendance.employee_id, employee)
        self.assertFalse(attendance.api_branch_id)

    def test_external_sync_skips_unmapped_employee(self):
        state, message = self.env[
            "hr.attendance.api.sync.service"
        ]._import_attendance_row(
            {
                "id": "external-attendance-missing-employee",
                "employee_id": "external-employee-1",
                "employee_number": "MISSING-001",
                "employee": {"email": "api.test@example.com"},
                "branch_id": "external-branch-1",
                "check_in": "2026-08-13T08:00:00+03:00",
            },
            {"company": self.company, "timezone": "Asia/Riyadh"},
        )
        self.assertEqual(state, "skipped")
        self.assertIn("not mapped", message)
        self.assertIn("MISSING-001", message)

    def test_settings_repair_and_reactivate_scheduled_pull(self):
        cron = self.env.ref(
            "hr_management_attend_api.ir_cron_pull_external_attendance"
        )
        cron.write({"active": False, "numbercall": 0})
        settings = self.env["res.config.settings"].create(
            {
                "attendance_api_source_enabled": True,
                "attendance_api_source_interval_minutes": 10,
            }
        )
        settings.set_values()
        self.assertTrue(cron.active)
        self.assertEqual(cron.numbercall, -1)
        self.assertEqual(cron.interval_number, 10)
        self.assertEqual(cron.interval_type, "minutes")
        self.assertFalse(cron.doall)
        self.assertTrue(cron.nextcall)

    def test_system_administrator_can_read_cross_company_sync_log(self):
        other_company = self.env["res.company"].create(
            {"name": "Attendance API Log Company"}
        )
        log = self.env["hr.attendance.api.sync.log"].sudo().create(
            {
                "name": "Cross-company attendance sync",
                "company_id": other_company.id,
                "state": "success",
                "trigger": "cron",
                "started_at": fields.Datetime.now(),
            }
        )
        administrator = self.env.ref("base.user_admin")
        visible_log = self.env["hr.attendance.api.sync.log"].with_user(
            administrator
        ).search([("id", "=", log.id)])
        self.assertEqual(visible_log, log)

    def test_external_request_retries_transient_connection_error(self):
        response = Mock(status_code=200, headers={})
        request_path = (
            "odoo.addons.hr_management_attend_api.models."
            "attendance_sync_service.http_requests.request"
        )
        sleep_path = (
            "odoo.addons.hr_management_attend_api.models."
            "attendance_sync_service.time.sleep"
        )
        with patch(
            request_path,
            side_effect=[http_requests.ConnectionError("temporary"), response],
        ) as request_mock, patch(sleep_path):
            result = self.env[
                "hr.attendance.api.sync.service"
            ]._send_request(
                "GET",
                "https://hr.example.test/api/admin/attendances",
                {"retry_attempts": 3},
                timeout=1,
            )
        self.assertIs(result, response)
        self.assertEqual(request_mock.call_count, 2)

    def test_external_response_envelopes(self):
        service = self.env["hr.attendance.api.sync.service"]
        self.assertEqual(
            service._extract_rows({"data": [{"id": 1}]}, ("attendances", "data")),
            [{"id": 1}],
        )
        self.assertEqual(
            service._extract_rows(
                {"attendances": {"data": [{"id": 2}]}},
                ("attendances", "data"),
            ),
            [{"id": 2}],
        )
        self.assertEqual(
            service._page_count(
                {"data": {"data": [{"id": 3}], "last_page": 4}}
            ),
            4,
        )

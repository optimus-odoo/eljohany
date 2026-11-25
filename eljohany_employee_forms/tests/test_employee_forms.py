from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import SavepointCase


class TestEmployeeForms(SavepointCase):
    REPORT_TEMPLATES = (
        ("report_job_offer_document", "عرض وظيفي"),
        ("report_work_commencement_document", "نموذج مباشرة عمل"),
        ("report_vehicle_handover_document", "نموذج استلام سيارة"),
        ("report_sim_handover_document", "نموذج استلام شريحة إلكترونية"),
        ("report_employee_information_document", "تقرير معلومات الموظف"),
        ("report_employee_warning_document", "نموذج إنذار موظف"),
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_from = cls.env.company
        cls.company_to = cls.env["res.company"].create({"name": "Destination Company"})
        cls.branch_from = cls.env["res.branch"].create(
            {"name": "Source Branch", "company_id": cls.company_from.id}
        )
        cls.branch_to = cls.env["res.branch"].create(
            {"name": "Destination Branch", "company_id": cls.company_to.id}
        )
        cls.branch_alternate = cls.env["res.branch"].create(
            {"name": "Alternate Source Branch", "company_id": cls.company_from.id}
        )
        manager_group = cls.env.ref(
            "eljohany_employee_forms.group_employee_forms_manager"
        )
        cls.manager_user = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Forms Manager",
                "login": "forms.manager.test",
                "email": "forms.manager@example.com",
                "company_id": cls.company_from.id,
                "company_ids": [Command.set((cls.company_from | cls.company_to).ids)],
                "branch_id": cls.branch_from.id,
                "branch_ids": [Command.set((cls.branch_from | cls.branch_to).ids)],
                "groups_id": [Command.link(manager_group.id)],
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Transfer Employee",
                "company_id": cls.company_from.id,
                "branch_id": cls.branch_from.id,
                "user_id": cls.manager_user.id,
                "identification_id": "TEST-IQAMA-001",
            }
        )
        cls.job = cls.env["hr.job"].create(
            {"name": "Forms Test Job", "company_id": cls.company_from.id}
        )
        cls.employee.job_id = cls.job

    def test_transfer_updates_employee_and_linked_user(self):
        transfer = self.env["hr.employee.transfer"].with_user(self.manager_user).create(
            {
                "employee_id": self.employee.id,
                "effective_date": fields.Date.today(),
                "reason": "Operational requirement",
                "to_company_id": self.company_to.id,
                "to_branch_id": self.branch_to.id,
            }
        )
        transfer.action_submit()
        transfer.action_approve_and_apply()

        self.assertEqual(transfer.state, "applied")
        self.assertEqual(self.employee.company_id, self.company_to)
        self.assertEqual(self.employee.branch_id, self.branch_to)
        self.assertEqual(self.manager_user.company_id, self.company_to)
        self.assertEqual(self.manager_user.branch_id, self.branch_to)
        self.assertIn(self.company_to, self.manager_user.company_ids)
        self.assertIn(self.branch_to, self.manager_user.branch_ids)

    def test_transfer_rejects_branch_from_another_company(self):
        with self.assertRaises(ValidationError):
            self.env["hr.employee.transfer"].with_user(self.manager_user).create(
                {
                    "employee_id": self.employee.id,
                    "effective_date": fields.Date.today(),
                    "reason": "Invalid destination",
                    "to_company_id": self.company_to.id,
                    "to_branch_id": self.branch_from.id,
                }
            )

    def test_future_transfer_waits_for_effective_date(self):
        transfer = self.env["hr.employee.transfer"].with_user(self.manager_user).create(
            {
                "employee_id": self.employee.id,
                "effective_date": fields.Date.today() + timedelta(days=2),
                "reason": "Planned future transfer",
                "to_company_id": self.company_to.id,
                "to_branch_id": self.branch_to.id,
            }
        )
        transfer.action_submit()
        transfer.action_approve_and_apply()

        self.assertEqual(transfer.state, "approved")
        self.assertEqual(self.employee.company_id, self.company_from)
        self.assertEqual(self.employee.branch_id, self.branch_from)

    def test_transfer_detects_stale_source_assignment(self):
        transfer = self.env["hr.employee.transfer"].with_user(self.manager_user).create(
            {
                "employee_id": self.employee.id,
                "effective_date": fields.Date.today(),
                "reason": "Transfer with stale source",
                "to_company_id": self.company_to.id,
                "to_branch_id": self.branch_to.id,
            }
        )
        transfer.action_submit()
        self.employee.sudo().write({"branch_id": self.branch_alternate.id})

        with self.assertRaises(ValidationError):
            transfer.action_approve_and_apply()

    def test_transfer_without_linked_user_still_updates_employee(self):
        employee = self.env["hr.employee"].create(
            {
                "name": "Employee Without Login",
                "company_id": self.company_from.id,
                "branch_id": self.branch_from.id,
            }
        )
        transfer = self.env["hr.employee.transfer"].with_user(self.manager_user).create(
            {
                "employee_id": employee.id,
                "effective_date": fields.Date.today(),
                "reason": "Transfer employee without system access",
                "to_company_id": self.company_to.id,
                "to_branch_id": self.branch_to.id,
            }
        )
        transfer.action_submit()
        transfer.action_approve_and_apply()

        self.assertEqual(transfer.state, "applied")
        self.assertEqual(employee.company_id, self.company_to)
        self.assertEqual(employee.branch_id, self.branch_to)

    def test_scheduled_transfer_records_application_failure(self):
        transfer = self.env["hr.employee.transfer"].with_user(self.manager_user).create(
            {
                "employee_id": self.employee.id,
                "effective_date": fields.Date.today() + timedelta(days=2),
                "reason": "Scheduled transfer with changed source",
                "to_company_id": self.company_to.id,
                "to_branch_id": self.branch_to.id,
            }
        )
        transfer.action_submit()
        transfer.action_approve_and_apply()
        self.employee.sudo().write({"branch_id": self.branch_alternate.id})
        transfer.write({"effective_date": fields.Date.today()})

        self.env["hr.employee.transfer"]._cron_apply_due_transfers()

        self.assertEqual(transfer.state, "application_failed")
        self.assertTrue(transfer.application_error)
        self.assertEqual(self.employee.branch_id, self.branch_alternate)

    def test_compensatory_leave_requires_employee_consent(self):
        start = fields.Datetime.now()
        assignment = self.env["hr.overtime.assignment"].with_user(self.manager_user).create(
            {
                "employee_id": self.employee.id,
                "company_id": self.company_from.id,
                "branch_id": self.branch_from.id,
                "start_datetime": start,
                "end_datetime": start + timedelta(hours=2),
                "assignment_reason": "Month-end work",
                "compensation_type": "comp_leave",
            }
        )
        assignment.action_submit()
        assignment.action_manager_approve()
        with self.assertRaises(ValidationError):
            assignment.action_approve()

        assignment.action_employee_consent()
        assignment.action_approve()
        self.assertEqual(assignment.state, "approved")
        self.assertEqual(assignment.compensatory_leave_hours, 3.0)

    def test_job_offer_dynamic_allowances_and_approval(self):
        today = fields.Date.today()
        offer = self.env["hr.job.offer"].with_user(self.manager_user).create(
            {
                "candidate_name": "New Candidate",
                "company_id": self.company_from.id,
                "branch_id": self.branch_from.id,
                "job_id": self.job.id,
                "expected_joining_date": today + timedelta(days=14),
                "offer_valid_until": today + timedelta(days=7),
                "basic_salary": 5000.0,
                "allowance_ids": [
                    Command.create(
                        {
                            "name": "Housing",
                            "frequency": "monthly",
                            "amount": 1500.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Joining Ticket",
                            "frequency": "one_time",
                            "amount": 1000.0,
                        }
                    ),
                ],
            }
        )

        self.assertEqual(offer.recurring_allowance_total, 1500.0)
        self.assertEqual(offer.one_time_allowance_total, 1000.0)
        self.assertEqual(offer.monthly_total, 6500.0)
        offer.action_submit()
        offer.action_approve()
        self.assertEqual(offer.state, "approved")
        self.assertTrue(offer.approved_by)

        with self.assertRaises(AccessError):
            offer.write({"basic_salary": 5500.0})

    def test_work_commencement_is_always_editable_and_keeps_branch(self):
        commencement = self.env["hr.work.commencement"].with_user(
            self.manager_user
        ).create(
            {
                "employee_id": self.employee.id,
                "commencement_date": fields.Date.today(),
                "work_location": "Original location",
            }
        )

        commencement.action_submit()
        commencement.write(
            {
                "branch_id": self.branch_alternate.id,
                "work_location": "Updated before approval",
                "notes": "Updated while submitted",
            }
        )
        commencement.action_approve()

        self.assertEqual(commencement.state, "approved")
        self.assertEqual(commencement.branch_id, self.branch_alternate)
        self.assertEqual(commencement.work_location, "Updated before approval")
        self.assertEqual(commencement.notes, "Updated while submitted")

        commencement.write(
            {
                "work_location": "Updated after approval",
                "notes": "Editable after approval",
            }
        )
        self.assertEqual(commencement.work_location, "Updated after approval")
        self.assertEqual(commencement.notes, "Editable after approval")

    def test_work_commencement_report_has_no_signature_section(self):
        template = self.env.ref(
            "eljohany_employee_forms.report_work_commencement_document"
        )

        self.assertNotIn("additional_form_signatures", template.arch_db)

    def test_all_print_templates_use_the_odoo_utf8_article_layout(self):
        for template_id, arabic_title in self.REPORT_TEMPLATES:
            arch = self.env.ref(
                f"eljohany_employee_forms.{template_id}"
            ).arch_db
            self.assertIn('t-call="web.html_container"', arch)
            self.assertIn('class="article"', arch)
            self.assertIn('t-att-data-oe-model="doc._name"', arch)
            self.assertIn('t-att-data-oe-id="doc.id"', arch)
            self.assertIn('t-translation="off"', arch)
            self.assertIn(arabic_title, arch)
            self.assertNotIn("Ø", arch)
            self.assertNotIn("Ù", arch)

    def test_sim_handover_updates_registry_and_return_releases_it(self):
        category = self.env["hr.mobile.sim.category"].with_user(
            self.manager_user
        ).create(
            {
                "name": "Business 100",
                "company_id": self.company_from.id,
                "monthly_price": 100.0,
            }
        )
        sim = self.env["hr.mobile.sim"].with_user(self.manager_user).create(
            {
                "mobile_number": "0500000001",
                "serial_number": "SIM-TEST-0001",
                "company_id": self.company_from.id,
                "category_id": category.id,
            }
        )
        handover = self.env["hr.mobile.sim.handover"].with_user(
            self.manager_user
        ).create(
            {
                "employee_id": self.employee.id,
                "sim_id": sim.id,
                "purpose": "Business communications",
                "acknowledgement": "<p>Employee accepts responsibility.</p>",
            }
        )

        handover.action_submit()
        handover.action_approve()
        self.assertEqual(sim.status, "assigned")
        self.assertEqual(sim.employee_id, self.employee)

        handover.write({"return_date": fields.Date.today()})
        handover.action_mark_returned()
        self.assertEqual(handover.state, "returned")
        self.assertEqual(sim.status, "available")
        self.assertFalse(sim.employee_id)

    def test_available_sim_can_keep_a_current_holder(self):
        category = self.env["hr.mobile.sim.category"].with_user(
            self.manager_user
        ).create(
            {
                "name": "Available With Holder",
                "company_id": self.company_from.id,
                "monthly_price": 100.0,
            }
        )

        sim = self.env["hr.mobile.sim"].with_user(self.manager_user).create(
            {
                "mobile_number": "0500000002",
                "serial_number": "SIM-TEST-0002",
                "company_id": self.company_from.id,
                "category_id": category.id,
                "employee_id": self.employee.id,
                "status": "available",
            }
        )

        self.assertEqual(sim.status, "available")
        self.assertEqual(sim.employee_id, self.employee)

    def test_employee_information_report_refreshes_snapshot_on_direct_print(self):
        report = self.env["hr.employee.information.report"].with_user(
            self.manager_user
        ).create(
            {
                "employee_id": self.employee.id,
                "purpose": "Official employee information",
            }
        )
        self.assertEqual(report.identification_id, "TEST-IQAMA-001")
        self.assertEqual(report.employee_name, self.employee.name)
        self.assertEqual(report.branch_id, self.branch_from)

        self.employee.sudo().identification_id = "CHANGED-AFTER-ISSUE"
        report.action_print()

        self.assertEqual(report.state, "draft")
        self.assertEqual(report.identification_id, "CHANGED-AFTER-ISSUE")

    def test_employee_information_report_collects_related_records(self):
        today = fields.Date.today()
        start = fields.Datetime.now()
        self.env["hr.custody"].sudo().create(
            {
                "employee_id": self.employee.id,
                "company_id": self.company_from.id,
                "description": "Laptop custody",
            }
        )
        self.env["hr.loan"].sudo().create(
            {
                "employee_id": self.employee.id,
                "loan_amount": 1200.0,
                "installment": 2,
                "payment_date": today,
            }
        )
        self.env["hr.overtime.assignment"].sudo().create(
            {
                "employee_id": self.employee.id,
                "company_id": self.company_from.id,
                "branch_id": self.branch_from.id,
                "start_datetime": start,
                "end_datetime": start + timedelta(hours=2),
                "assignment_reason": "Inventory count",
            }
        )
        category = self.env["hr.mobile.sim.category"].sudo().create(
            {
                "name": "Employee Report SIM Category",
                "company_id": self.company_from.id,
                "monthly_price": 100.0,
            }
        )
        sim = self.env["hr.mobile.sim"].sudo().create(
            {
                "mobile_number": "0500000099",
                "serial_number": "SIM-REPORT-0099",
                "company_id": self.company_from.id,
                "category_id": category.id,
            }
        )
        self.env["hr.mobile.sim.handover"].sudo().create(
            {
                "employee_id": self.employee.id,
                "sim_id": sim.id,
                "purpose": "Business communications",
                "acknowledgement": "<p>Accepted.</p>",
            }
        )
        brand = self.env["fleet.vehicle.model.brand"].sudo().create(
            {"name": "Employee Report Brand"}
        )
        vehicle_model = self.env["fleet.vehicle.model"].sudo().create(
            {"name": "Employee Report Model", "brand_id": brand.id}
        )
        vehicle = self.env["fleet.vehicle"].sudo().create(
            {"model_id": vehicle_model.id, "license_plate": "REPORT-001"}
        )
        self.env["hr.vehicle.handover"].sudo().create(
            {
                "employee_id": self.employee.id,
                "vehicle_id": vehicle.id,
                "handover_date": today,
                "odometer": 100.0,
                "fuel_level": "full",
                "vehicle_condition": "Good",
            }
        )
        self.env["hr.employee.warning"].sudo().create(
            {
                "employee_id": self.employee.id,
                "warning_date": today,
                "violation_date": today,
                "subject": "Policy violation",
                "details": "Test warning details.",
                "penalty_type": "notice",
                "penalty_description": "Written notice.",
            }
        )
        report = self.env["hr.employee.information.report"].with_user(
            self.manager_user
        ).create(
            {
                "employee_id": self.employee.id,
                "purpose": "Complete employee information",
            }
        )

        related = report._get_employee_related_information()

        self.assertEqual(len(related["custodies"]), 1)
        self.assertEqual(len(related["loans"]), 1)
        self.assertEqual(len(related["assignments"]), 1)
        self.assertEqual(len(related["sim_handovers"]), 1)
        self.assertEqual(len(related["vehicle_handovers"]), 1)
        self.assertEqual(len(related["warnings"]), 1)
        for records in related.values():
            self.assertEqual(records.mapped("employee_id"), self.employee)
            self.assertEqual(records.mapped("company_id"), self.company_from)

    def test_warning_captures_employee_branch_job_and_identification(self):
        warning = self.env["hr.employee.warning"].with_user(
            self.manager_user
        ).create(
            {
                "employee_id": self.employee.id,
                "warning_date": fields.Date.today(),
                "violation_date": fields.Date.today(),
                "subject": "Attendance violation",
                "details": "Repeated unexcused lateness.",
                "penalty_type": "notice",
                "penalty_description": "Written notice.",
            }
        )

        self.assertEqual(warning.branch_id, self.branch_from)
        self.assertEqual(warning.job_id, self.job)
        self.assertEqual(warning.identification_id, "TEST-IQAMA-001")

        warning.action_submit()
        warning.action_approve()
        warning.write(
            {
                "delivery_date": fields.Date.today(),
                "employee_response": "Warning received and acknowledged.",
            }
        )
        self.assertEqual(warning.state, "approved")
        self.assertTrue(warning.delivery_date)

        with self.assertRaises(AccessError):
            warning.write({"subject": "Changed after approval"})

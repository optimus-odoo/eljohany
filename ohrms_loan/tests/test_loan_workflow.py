from odoo import fields
from dateutil.relativedelta import relativedelta

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import SavepointCase


@tagged("post_install", "-at_install")
class TestLoanWorkflow(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Loan Workflow Company"})
        internal_group = cls.env.ref("base.group_user")
        employee_group = cls.env.ref("ohrms_loan.group_employee_forms_access")

        def make_user(name, login, groups):
            return cls.env["res.users"].with_context(no_reset_password=True).create(
                {
                    "name": name,
                    "login": login,
                    "email": "%s@example.com" % login,
                    "company_id": cls.company.id,
                    "company_ids": [(6, 0, [cls.company.id])],
                    "groups_id": [(6, 0, groups)],
                }
            )

        cls.employee_user = make_user(
            "Loan Employee",
            "loan.employee",
            [internal_group.id, employee_group.id],
        )
        cls.approver_1 = make_user(
            "First Approver", "loan.approver.1", [internal_group.id]
        )
        cls.approver_2 = make_user(
            "Second Approver", "loan.approver.2", [internal_group.id]
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Loan Employee",
                "user_id": cls.employee_user.id,
                "company_id": cls.company.id,
            }
        )
        cls.workflow = cls.env["hr.loan.workflow"].create(
            {"name": "Company Loan Workflow", "company_id": cls.company.id}
        )
        cls.step_1 = cls.env["hr.loan.workflow.step"].create(
            {
                "workflow_id": cls.workflow.id,
                "sequence": 10,
                "name": "Direct Manager Approval",
                "approver_id": cls.approver_1.id,
            }
        )
        cls.step_2 = cls.env["hr.loan.workflow.step"].create(
            {
                "workflow_id": cls.workflow.id,
                "sequence": 20,
                "name": "HR Approval",
                "approver_id": cls.approver_2.id,
            }
        )

    def _create_loan(self, **extra_values):
        values = {
            "employee_id": self.employee.id,
            "loan_amount": 12000,
            "installment": 12,
            "payment_date": fields.Date.today(),
        }
        values.update(extra_values)
        return (
            self.env["hr.loan"]
            .with_user(self.employee_user)
            .with_company(self.company)
            .create(values)
        )

    def _set_approved_with_outstanding_balance(self, loan):
        loan.with_context(loan_workflow_action=True).write({"state": "approve"})
        loan.with_context(loan_workflow_action=True).action_compute_installment()

    def test_company_workflow_sequence_and_arabic_activities(self):
        loan = self._create_loan()
        loan.with_user(self.employee_user).action_submit()

        self.assertEqual(loan.workflow_id, self.workflow)
        self.assertEqual(len(loan.approval_line_ids), 2)
        self.assertEqual(loan.current_approver_id, self.approver_1)
        self.assertEqual(loan.current_step_name, "Direct Manager Approval")

        activity = self.env["mail.activity"].sudo().search(
            [
                ("res_model", "=", "hr.loan"),
                ("res_id", "=", loan.id),
                ("user_id", "=", self.approver_1.id),
            ],
            limit=1,
        )
        self.assertEqual(activity.summary, "مطلوب إجراء على طلب سلفة")
        self.assertIn("المرحلة", activity.note)

        with self.assertRaises(AccessError):
            loan.with_user(self.employee_user).write({"loan_amount": 15000})

        loan.with_user(self.approver_1).action_workflow_approve()
        self.assertEqual(loan.current_approver_id, self.approver_2)
        self.assertEqual(loan.approval_line_ids[0].status, "approved")
        self.assertEqual(loan.approval_line_ids[1].status, "waiting")

        loan.with_user(self.approver_2).action_workflow_approve()
        self.assertEqual(loan.state, "approve")
        self.assertFalse(loan.current_approval_line_id)
        self.assertEqual(len(loan.loan_lines), 12)
        self.assertAlmostEqual(sum(loan.loan_lines.mapped("amount")), 12000)

    def test_only_current_assignee_can_approve(self):
        loan = self._create_loan()
        loan.with_user(self.employee_user).action_submit()
        with self.assertRaises(AccessError):
            loan.with_user(self.approver_2).action_workflow_approve()

    def test_employee_company_cannot_be_overridden(self):
        other_company = self.env["res.company"].create({"name": "Other Company"})
        loan = (
            self.env["hr.loan"]
            .with_user(self.employee_user)
            .with_company(self.company)
            .create(
                {
                    "employee_id": self.employee.id,
                    "company_id": other_company.id,
                    "loan_amount": 1000,
                    "installment": 1,
                    "payment_date": fields.Date.today(),
                }
            )
        )
        self.assertEqual(loan.company_id, self.company)

    def test_payslip_period_returns_only_due_installments(self):
        loan = (
            self.env["hr.loan"]
            .with_user(self.employee_user)
            .with_company(self.company)
            .create(
                {
                    "employee_id": self.employee.id,
                    "loan_amount": 3000,
                    "installment": 3,
                    "payment_date": fields.Date.from_string("2026-01-15"),
                }
            )
        )
        loan.with_context(loan_workflow_action=True).write({"state": "approve"})
        loan.with_context(loan_workflow_action=True).action_compute_installment()

        january_payslip = self.env["hr.payslip"].new(
            {
                "employee_id": self.employee.id,
                "company_id": self.company.id,
                "date_from": fields.Date.from_string("2026-01-01"),
                "date_to": fields.Date.from_string("2026-01-31"),
            }
        )
        due_lines = january_payslip._get_due_loan_lines()
        self.assertEqual(len(due_lines), 1)
        self.assertEqual(due_lines.date, fields.Date.from_string("2026-01-15"))
        self.assertEqual(sum(due_lines.mapped("amount")), 1000)

        due_lines.paid = True
        self.assertFalse(january_payslip._get_due_loan_lines())

    def test_unpaid_loan_blocks_request_until_six_calendar_months(self):
        today = fields.Date.today()
        previous = self._create_loan(
            date=today - relativedelta(months=6) + relativedelta(days=1)
        )
        self._set_approved_with_outstanding_balance(previous)

        with self.assertRaisesRegex(ValidationError, "six calendar months"):
            self._create_loan()

    def test_unpaid_loan_allows_request_on_six_month_boundary(self):
        previous_date = fields.Date.from_string("2026-01-31")
        previous = self._create_loan(date=previous_date)
        self._set_approved_with_outstanding_balance(previous)

        previous_loan, eligible_date, is_eligible = (
            self.env["hr.loan"]._get_repeat_loan_eligibility(
                self.employee,
                reference_date=fields.Date.from_string("2026-07-31"),
            )
        )
        self.assertEqual(previous_loan, previous)
        self.assertEqual(eligible_date, fields.Date.from_string("2026-07-31"))
        self.assertTrue(is_eligible)
        with self.assertRaisesRegex(ValidationError, "2026-07-31"):
            self.env["hr.loan"]._check_repeat_loan_eligibility(
                self.employee,
                reference_date=fields.Date.from_string("2026-07-30"),
            )

    def test_paid_loan_does_not_impose_waiting_period(self):
        today = fields.Date.today()
        previous = self._create_loan(date=today - relativedelta(days=1))
        self._set_approved_with_outstanding_balance(previous)
        previous.loan_lines.write({"paid": True})

        self.assertFalse(previous.balance_amount)
        self.assertTrue(self._create_loan())

    def test_submission_rechecks_eligibility(self):
        draft = self._create_loan()
        competing = self._create_loan()
        self._set_approved_with_outstanding_balance(competing)

        with self.assertRaisesRegex(ValidationError, "six calendar months"):
            draft.action_submit()

    def test_final_approval_rechecks_after_competing_loan(self):
        first = self._create_loan()
        second = self._create_loan()
        first.action_submit()
        second.action_submit()

        first.with_user(self.approver_1).action_workflow_approve()
        first.with_user(self.approver_2).action_workflow_approve()
        second.with_user(self.approver_1).action_workflow_approve()
        with self.assertRaisesRegex(ValidationError, "six calendar months"):
            second.with_user(self.approver_2).action_workflow_approve()

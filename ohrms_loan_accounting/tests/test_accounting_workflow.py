from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import SavepointCase


@tagged("post_install", "-at_install")
class TestLoanAccountingWorkflow(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {"name": "Loan Accounting Workflow Company"}
        )
        cls.account_user = cls.env["res.users"].with_context(
            no_reset_password=True
        ).create(
            {
                "name": "Loan Accountant",
                "login": "loan.accountant",
                "email": "loan.accountant@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("account.group_account_user").id,
                        ],
                    )
                ],
            }
        )
        cls.approver = cls.env["res.users"].with_context(
            no_reset_password=True
        ).create(
            {
                "name": "Loan General Approver",
                "login": "loan.general.approver",
                "email": "loan.general.approver@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def test_accounting_step_is_unique_and_final(self):
        workflow = self.env["hr.loan.workflow"].create(
            {"name": "Accounting Route", "company_id": self.company.id}
        )
        self.env["hr.loan.workflow.step"].create(
            {
                "workflow_id": workflow.id,
                "sequence": 10,
                "name": "Manager Approval",
                "approver_id": self.approver.id,
            }
        )
        accounting_step = self.env["hr.loan.workflow.step"].create(
            {
                "workflow_id": workflow.id,
                "sequence": 20,
                "name": "Accounting and Posting",
                "approver_id": self.account_user.id,
                "step_type": "accounting",
            }
        )
        self.assertEqual(accounting_step.step_type, "accounting")
        with self.assertRaises(ValidationError):
            self.env["hr.loan.workflow.step"].create(
                {
                    "workflow_id": workflow.id,
                    "sequence": 30,
                    "name": "Invalid Later Approval",
                    "approver_id": self.approver.id,
                }
            )

    def test_accounting_step_requires_accounting_user(self):
        other_company = self.env["res.company"].create(
            {"name": "Invalid Loan Accounting Company"}
        )
        self.approver.write({"company_ids": [(4, other_company.id)]})
        workflow = self.env["hr.loan.workflow"].create(
            {"name": "Invalid Accounting Route", "company_id": other_company.id}
        )
        with self.assertRaises(ValidationError):
            self.env["hr.loan.workflow.step"].create(
                {
                    "workflow_id": workflow.id,
                    "sequence": 10,
                    "name": "Accounting",
                    "approver_id": self.approver.id,
                    "step_type": "accounting",
                }
            )

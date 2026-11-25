# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    loan_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Loan Currency",
        readonly=True,
    )
    loan_due_amount = fields.Monetary(
        string="Due Loan Installments",
        currency_field="loan_currency_id",
        compute="_compute_loan_due_summary",
        help="Total unpaid approved loan installments due within this payslip period.",
    )
    loan_due_count = fields.Integer(
        string="Due Installment Count",
        compute="_compute_loan_due_summary",
    )

    def _get_due_loan_lines(self):
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
            return self.env["hr.loan.line"]
        due_lines = self.env["hr.loan.line"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("loan_id.company_id", "=", self.company_id.id),
                ("loan_id.state", "=", "approve"),
                ("paid", "=", False),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
            ],
            order="date, id",
        )
        if not due_lines:
            return due_lines
        reservation_domain = [
            ("loan_line_id", "in", due_lines.ids),
            ("payslip_id.state", "not in", ("cancel",)),
        ]
        if self.id:
            reservation_domain.append(("payslip_id", "!=", self.id))
        reserved_line_ids = (
            self.env["hr.payslip.input"]
            .search(reservation_domain)
            .mapped("loan_line_id")
            .ids
        )
        return due_lines.filtered(lambda line: line.id not in reserved_line_ids)

    @api.depends(
        "employee_id",
        "company_id",
        "date_from",
        "date_to",
        "state",
        "input_line_ids.amount",
        "input_line_ids.loan_line_id",
    )
    def _compute_loan_due_summary(self):
        for payslip in self:
            loan_inputs = payslip.input_line_ids.filtered("loan_line_id")
            if loan_inputs:
                payslip.loan_due_amount = sum(loan_inputs.mapped("amount"))
                payslip.loan_due_count = len(loan_inputs)
            else:
                due_lines = payslip._get_due_loan_lines()
                payslip.loan_due_amount = sum(due_lines.mapped("amount"))
                payslip.loan_due_count = len(due_lines)

    def _sync_loan_inputs(self):
        """Synchronize only installments due inside each payslip period."""
        input_type = self.env.ref("ohrms_loan.hr_loan_input_type")
        for payslip in self.filtered(
            lambda slip: slip.id and slip.state in ("draft", "verify")
        ):
            due_lines = payslip._get_due_loan_lines()
            if due_lines:
                self.env.cr.execute(
                    "SELECT id FROM hr_loan_line WHERE id IN %s FOR UPDATE",
                    [tuple(due_lines.ids)],
                )
                due_lines = payslip._get_due_loan_lines()
            existing_inputs = payslip.input_line_ids.filtered("loan_line_id")
            stale_inputs = existing_inputs.filtered(
                lambda input_line: input_line.loan_line_id not in due_lines
            )
            stale_inputs.unlink()
            current_inputs = existing_inputs - stale_inputs
            duplicate_inputs = self.env["hr.payslip.input"]
            seen_installments = set()
            for input_line in current_inputs:
                installment_id = input_line.loan_line_id.id
                if installment_id in seen_installments:
                    duplicate_inputs |= input_line
                else:
                    seen_installments.add(installment_id)
            duplicate_inputs.unlink()
            current_inputs -= duplicate_inputs
            current_by_installment = {
                input_line.loan_line_id.id: input_line
                for input_line in current_inputs
            }
            for loan_line in due_lines:
                values = {
                    "input_type_id": input_type.id,
                    "amount": loan_line.amount,
                    "date_from": payslip.date_from,
                    "date_to": payslip.date_to,
                }
                existing = current_by_installment.get(loan_line.id)
                if existing:
                    existing.write(values)
                else:
                    values.update(
                        {
                            "payslip_id": payslip.id,
                            "loan_line_id": loan_line.id,
                        }
                    )
                    self.env["hr.payslip.input"].create(values)
            payslip.invalidate_recordset(["loan_due_amount", "loan_due_count"])
        return True

    @api.model_create_multi
    def create(self, vals_list):
        payslips = super().create(vals_list)
        payslips._sync_loan_inputs()
        return payslips

    def write(self, vals):
        result = super().write(vals)
        if {"employee_id", "company_id", "date_from", "date_to"} & set(vals):
            self._sync_loan_inputs()
        return result

    def compute_sheet(self):
        self._sync_loan_inputs()
        return super().compute_sheet()

    def action_refresh_loan_installments(self):
        if any(payslip.state not in ("draft", "verify") for payslip in self):
            raise UserError(
                _("Loan installments can only be refreshed on draft payslips.")
            )
        self._sync_loan_inputs()
        amount = sum(self.mapped("loan_due_amount"))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Loan installments updated"),
                "message": _(
                    "The due loan amount for this payslip period is %(amount).2f.",
                    amount=amount,
                ),
                "type": "success",
                "sticky": True,
            },
        }

    def action_payslip_done(self):
        result = super().action_payslip_done()
        for payslip in self:
            loan_lines = payslip.input_line_ids.filtered(
                "loan_line_id"
            ).mapped("loan_line_id")
            if loan_lines:
                loan_lines.write(
                    {"paid": True, "payslip_id": payslip.id}
                )
                loan_lines.mapped("loan_id")._compute_total_amount()
        return result

    def action_payslip_cancel(self):
        loan_lines = self.input_line_ids.filtered("loan_line_id").mapped(
            "loan_line_id"
        )
        result = super().action_payslip_cancel()
        if loan_lines:
            loan_lines.write({"paid": False, "payslip_id": False})
            loan_lines.mapped("loan_id")._compute_total_amount()
        return result

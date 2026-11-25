# -*- coding: utf-8 -*-
from datetime import datetime, time

import babel

from odoo import _, fields, models, tools


class HrPayslipAcc(models.Model):
    _inherit = "hr.payslip"

    def action_payslip_done(self):
        result = super().action_payslip_done()
        for payslip in self:
            period_start = datetime.combine(
                fields.Date.from_string(payslip.date_from),
                time.min,
            )
            locale = self.env.context.get("lang") or "en_US"
            month = tools.ustr(
                babel.dates.format_date(
                    date=period_start,
                    format="MMMM-y",
                    locale=locale,
                )
            )
            for input_line in payslip.input_line_ids.filtered("loan_line_id"):
                input_line.loan_line_id.action_paid_amount(month)
        return result

    def action_payslip_cancel(self):
        loan_lines = self.input_line_ids.filtered("loan_line_id").mapped(
            "loan_line_id"
        )
        moves_by_line = [
            (line, line.sudo().payment_move_id)
            for line in loan_lines
            if line.sudo().payment_move_id
        ]
        result = super().action_payslip_cancel()
        for line, move in moves_by_line:
            if move.state == "posted":
                move.sudo()._reverse_moves(
                    [
                        {
                            "date": fields.Date.context_today(self),
                            "ref": _("Reversal of %s") % move.name,
                        }
                    ],
                    cancel=True,
                )
            line.sudo().payment_move_id = False
        return result

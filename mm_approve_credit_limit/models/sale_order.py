from odoo import api, fields, models
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    credit_limit_approved = fields.Boolean(default=False)
    check_if_credit_limit = fields.Boolean(compute="_compute_check_if_credit_limit")

    def button_approve_credit_limit(self):
        for rec in self:
            rec.credit_limit_approved = True

    @api.depends('partner_id', 'amount_total', 'credit_limit_approved')
    def _compute_check_if_credit_limit(self):
        for rec in self:
            rec.check_if_credit_limit = False

            if rec.credit_limit_approved:
                rec.check_if_credit_limit = False

            elif not rec.credit_limit_approved and rec.partner_id.use_partner_credit_limit:
                credit_limit = rec.partner_id.credit_limit
                current_credit = rec.partner_id.credit
                remaining_credit = credit_limit - current_credit

                if rec.amount_total > remaining_credit:
                    rec.check_if_credit_limit = True

    def send_activity(self):
        group = self.env.ref('edit_sale_order.group_approve_partner_credit_limit')
        for user in group.users:
            activity = self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary="Approval Required",
                note="Please review and approve partner credit limit in this sale order.",
                date_deadline=fields.Date.today() + relativedelta(days=1)
            )
            print(activity, 'activity')

    def action_confirm(self):
        for rec in self:
            if rec.partner_id.use_partner_credit_limit:
                credit_limit = rec.partner_id.credit_limit
                current_credit = rec.partner_id.credit
                remaining_credit = credit_limit - current_credit

                if rec.amount_total > remaining_credit:
                    if not self.env.user.has_group(
                            'edit_sale_order.group_approve_partner_credit_limit') and not rec.credit_limit_approved:
                        rec.send_activity()
                        raise ValidationError(
                            f"You can't confirm the order {rec.name} because the customer's remaining credit "
                            f"({remaining_credit:.2f}) is less than the order total ({rec.amount_total:.2f}).\n"
                            f"Approval request has been sent to the responsible team."
                        )

        return super().action_confirm()

    def action_draft(self):
        for rec in self:
            rec.credit_limit_approved = False
        return super().action_draft()

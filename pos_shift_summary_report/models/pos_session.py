from odoo import fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    closed_by_id = fields.Many2one(
        "res.users",
        string="Closed By",
        readonly=True,
        copy=False,
        help="User who successfully completed the POS session closing process.",
    )

    def _get_closing_shift_report_filename(self):
        self.ensure_one()
        if not self.start_at:
            return "POS_Shift_%s" % (self.name or self.id)
        timezone = self.env.context.get("tz") or self.env.user.tz or "UTC"
        start_at = fields.Datetime.context_timestamp(
            self.with_context(tz=timezone), self.start_at
        )
        report_end = self.stop_at or fields.Datetime.now()
        stop_at = fields.Datetime.context_timestamp(
            self.with_context(tz=timezone), report_end
        )
        return "POS_Shift_%s_%s" % (
            start_at.strftime("%Y%m%d_%H%M%S"),
            stop_at.strftime("%Y%m%d_%H%M%S"),
        )

    def _validate_session(
        self,
        balancing_account=False,
        amount_to_balance=0,
        bank_payment_method_diffs=None,
    ):
        result = super()._validate_session(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )
        if self.state == "closed" and not self.closed_by_id:
            self.closed_by_id = self.env.user
        return result

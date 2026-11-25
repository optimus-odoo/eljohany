from collections import defaultdict
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class PosShiftSummaryReportWizard(models.TransientModel):
    _name = "pos.shift.summary.report.wizard"
    _description = "POS Shift Summary Report Wizard"

    def _default_date_from(self):
        """Return local midnight converted to the UTC-naive value Odoo stores."""
        today = fields.Date.context_today(self)
        timezone = pytz.timezone(
            self.env.context.get("tz") or self.env.user.tz or "UTC"
        )
        start_local = timezone.localize(datetime.combine(today, time.min))
        return start_local.astimezone(pytz.UTC).replace(tzinfo=None)

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    pos_config_ids = fields.Many2many(
        "pos.config",
        "pos_shift_summary_report_config_rel",
        "wizard_id",
        "config_id",
        string="Points of Sale",
        required=True,
        check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    session_ids = fields.Many2many(
        "pos.session",
        "pos_shift_summary_report_session_rel",
        "wizard_id",
        "session_id",
        string="POS Sessions",
        readonly=True,
        check_company=True,
    )
    date_from = fields.Datetime(
        string="Date and Time From",
        required=True,
        default=_default_date_from,
    )
    date_to = fields.Datetime(
        string="Date and Time To",
        required=True,
        default=fields.Datetime.now,
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for wizard in self:
            wizard.pos_config_ids = wizard.pos_config_ids.filtered(
                lambda config: config.company_id == wizard.company_id
            )
            wizard.session_ids = wizard.session_ids.filtered(
                lambda session: session.config_id.company_id == wizard.company_id
            )

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(
                    _(
                        "Date and Time From must be before or equal to "
                        "Date and Time To."
                    )
                )

    @api.constrains("company_id", "pos_config_ids")
    def _check_pos_companies(self):
        for wizard in self:
            invalid_configs = wizard.pos_config_ids.filtered(
                lambda config: config.company_id != wizard.company_id
            )
            if invalid_configs:
                raise ValidationError(
                    _("All selected Points of Sale must belong to the selected company.")
                )
            invalid_sessions = wizard.session_ids.filtered(
                lambda session: (
                    session.config_id.company_id != wizard.company_id
                    or session.config_id not in wizard.pos_config_ids
                )
            )
            if invalid_sessions:
                raise ValidationError(
                    _(
                        "All selected POS Sessions must belong to the selected "
                        "company and Points of Sale."
                    )
                )

    def _validate_report_options(self):
        self.ensure_one()
        self._check_date_range()
        self._check_pos_companies()
        if self.company_id not in self.env.user.company_ids:
            raise AccessError(_("You are not allowed to report on the selected company."))
        if not self.pos_config_ids:
            raise UserError(_("Select at least one Point of Sale."))

    def _get_utc_datetime_bounds(self):
        self.ensure_one()
        return (
            fields.Datetime.to_string(self.date_from),
            fields.Datetime.to_string(self.date_to),
        )

    def _format_report_datetime(self, value):
        self.ensure_one()
        if not value:
            return ""
        local_value = fields.Datetime.context_timestamp(self, value)
        return local_value.strftime("%Y-%m-%d %H:%M:%S")

    def _get_order_domain(self):
        self.ensure_one()
        start_utc, end_utc = self._get_utc_datetime_bounds()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("config_id", "in", self.pos_config_ids.ids),
            ("state", "in", ["paid", "done", "invoiced"]),
            ("date_order", ">=", start_utc),
            ("date_order", "<=", end_utc),
        ]
        if self.session_ids:
            domain.append(("session_id", "in", self.session_ids.ids))
        return domain

    def _get_session_domain(self):
        """Return sessions that overlap any part of the selected period."""
        self.ensure_one()
        start_utc, end_utc = self._get_utc_datetime_bounds()
        domain = [
            ("config_id.company_id", "=", self.company_id.id),
            ("config_id", "in", self.pos_config_ids.ids),
            ("start_at", "!=", False),
            ("start_at", "<=", end_utc),
            "|",
            ("stop_at", "=", False),
            ("stop_at", ">=", start_utc),
        ]
        if self.session_ids:
            domain.append(("id", "in", self.session_ids.ids))
        return domain

    @api.model
    def _split_signed_amounts(self, amounts):
        positive = sum(amount for amount in amounts if amount > 0.0)
        negative = -sum(amount for amount in amounts if amount < 0.0)
        return {
            "positive": positive,
            "negative": negative,
            "net": positive - negative,
        }

    @api.model
    def _build_sales_totals(self, order_amounts, discounts):
        """Return gross, refund, discount, and net sales on one tax basis.

        ``order_amounts`` are tax-included order totals after line discounts.
        Odoo's line discount helper is also tax-included, so adding it back
        produces gross sales before discounts without mixing tax bases.
        """
        split = self._split_signed_amounts(order_amounts)
        gross_sales = split["positive"] + discounts
        return {
            "gross_sales": gross_sales,
            "refunds": split["negative"],
            "discounts": discounts,
            "net_sales": gross_sales - discounts - split["negative"],
        }

    def _order_amount_to_company_currency(self, order, amount):
        """Use the rate stored on the order, not a later currency-table rate."""
        self.ensure_one()
        return amount / (order.currency_rate or 1.0)

    def _session_amount_to_company_currency(self, session, amount, value_date=None):
        self.ensure_one()
        currency = session.currency_id
        target_currency = self.company_id.currency_id
        if currency == target_currency:
            return amount
        return currency._convert(
            amount,
            target_currency,
            self.company_id,
            value_date or fields.Date.context_today(self),
        )

    def _prepare_sales_summary(self, orders):
        self.ensure_one()
        converted_totals = [
            self._order_amount_to_company_currency(order, order.amount_total)
            for order in orders
        ]
        discounts = 0.0
        for line in orders.lines.filtered(
            lambda report_line: report_line.qty > 0 and report_line.discount > 0
        ):
            discounts += self._order_amount_to_company_currency(
                line.order_id,
                line._get_discount_amount(),
            )
        sales_totals = self._build_sales_totals(converted_totals, discounts)

        taxes = sum(
            self._order_amount_to_company_currency(order, order.amount_tax)
            for order in orders
        )
        cash_rounding = sum(
            self._order_amount_to_company_currency(
                order,
                order.amount_paid - order.amount_total,
            )
            for order in orders
        )
        return {
            **sales_totals,
            "taxes": taxes,
            "cash_rounding": cash_rounding,
            "sales_count": len(orders.filtered(lambda order: order.amount_total >= 0)),
            "refund_count": len(orders.filtered(lambda order: order.amount_total < 0)),
        }

    def _prepare_payment_summary(self, orders):
        self.ensure_one()
        totals_by_method = defaultdict(float)
        payments = orders.payment_ids.filtered(
            lambda payment: payment.payment_method_id.type != "pay_later"
        )
        for payment in payments:
            totals_by_method[payment.payment_method_id.display_name] += (
                self._order_amount_to_company_currency(
                    payment.pos_order_id,
                    payment.amount,
                )
            )
        return [
            {"name": name, "amount": amount}
            for name, amount in sorted(
                totals_by_method.items(), key=lambda item: item[0].casefold()
            )
        ]

    def _cash_move_is_manual(self, cash_move, session):
        if cash_move.journal_id != session.cash_journal_id:
            return False

        # ``counterpart_account_id`` is only an input accepted by
        # account.bank.statement.line.create(); it is not a stored field on
        # the resulting statement line.  Closing-difference lines can instead
        # be identified by the journal's configured profit/loss accounts.
        difference_accounts = (
            session.cash_journal_id.profit_account_id
            | session.cash_journal_id.loss_account_id
        )
        return not bool(cash_move.move_id.line_ids.account_id & difference_accounts)

    def _prepare_session_lines(self, sessions):
        self.ensure_one()
        if not sessions:
            return []

        valid_states = ["paid", "done", "invoiced"]
        cash_payments = self.env["pos.payment"].search(
            [
                ("session_id", "in", sessions.ids),
                ("pos_order_id.state", "in", valid_states),
                ("payment_method_id.is_cash_count", "=", True),
            ],
            order="payment_date, id",
        )
        statement_lines = self.env["account.bank.statement.line"].sudo().search(
            [("pos_session_id", "in", sessions.ids)], order="create_date, id"
        )

        payments_by_session = defaultdict(list)
        for payment in cash_payments:
            payments_by_session[payment.session_id.id].append(payment)

        moves_by_session = defaultdict(list)
        for cash_move in statement_lines:
            session = cash_move.pos_session_id
            if self._cash_move_is_manual(cash_move, session):
                moves_by_session[session.id].append(cash_move)

        selected_start = fields.Datetime.to_datetime(self.date_from)
        selected_end = fields.Datetime.to_datetime(self.date_to)
        state_labels = {
            "opening_control": "جاري فتح المناوبة",
            "opened": "مفتوحة",
            "closing_control": "جاري الإغلاق",
            "closed": "مغلقة",
        }
        result = []
        for session in sessions.sorted(key=lambda item: (item.start_at or selected_start, item.id)):
            session_start = fields.Datetime.to_datetime(session.start_at) or selected_start
            session_stop = fields.Datetime.to_datetime(session.stop_at) if session.stop_at else None
            segment_start = max(selected_start, session_start)
            segment_end = min(selected_end, session_stop or selected_end)
            if segment_start > segment_end:
                continue

            prior_cash_amounts = []
            period_cash_amounts = []
            for payment in payments_by_session[session.id]:
                payment_date = fields.Datetime.to_datetime(payment.payment_date)
                converted_amount = self._order_amount_to_company_currency(
                    payment.pos_order_id, payment.amount
                )
                if payment_date < segment_start:
                    prior_cash_amounts.append(converted_amount)
                elif payment_date <= segment_end:
                    period_cash_amounts.append(converted_amount)

            prior_move_amounts = []
            period_move_amounts = []
            for cash_move in moves_by_session[session.id]:
                move_datetime = fields.Datetime.to_datetime(cash_move.create_date)
                converted_amount = self._session_amount_to_company_currency(
                    session,
                    cash_move.amount,
                    cash_move.date,
                )
                if move_datetime < segment_start:
                    prior_move_amounts.append(converted_amount)
                elif move_datetime <= segment_end:
                    period_move_amounts.append(converted_amount)

            payment_split = self._split_signed_amounts(period_cash_amounts)
            move_split = self._split_signed_amounts(period_move_amounts)
            opening_balance = self._session_amount_to_company_currency(
                session,
                session.cash_register_balance_start,
                session_start.date(),
            ) + sum(prior_cash_amounts) + sum(prior_move_amounts)
            expected_balance = (
                opening_balance + payment_split["net"] + move_split["net"]
            )

            covers_session_end = bool(
                session_stop
                and session.state == "closed"
                and selected_end >= session_stop
            )
            covers_full_session = selected_start <= session_start and covers_session_end
            actual_balance = None
            difference = None
            if covers_session_end and session.cash_control:
                actual_balance = self._session_amount_to_company_currency(
                    session,
                    session.cash_register_balance_end_real,
                    session_stop.date(),
                )
                if covers_full_session:
                    expected_balance = self._session_amount_to_company_currency(
                        session,
                        session.cash_register_balance_end,
                        session_stop.date(),
                    )
                difference = actual_balance - expected_balance

            result.append(
                {
                    "name": session.name,
                    "pos_name": session.config_id.display_name,
                    "state": state_labels.get(session.state, session.state),
                    "opened_by": session.user_id.display_name,
                    "closed_by": session.closed_by_id.display_name or "غير مسجل",
                    "opened_at": self._format_report_datetime(session.start_at),
                    "closed_at": self._format_report_datetime(session.stop_at)
                    if session.stop_at
                    else "لم تغلق بعد",
                    "segment_from": self._format_report_datetime(segment_start),
                    "segment_to": self._format_report_datetime(segment_end),
                    "is_partial": not covers_full_session,
                    "cash_control": session.cash_control,
                    "opening_balance": opening_balance,
                    "cash_payments": payment_split["positive"],
                    "cash_refunds": payment_split["negative"],
                    "cash_in": move_split["positive"],
                    "cash_out": move_split["negative"],
                    "expected_balance": expected_balance,
                    "actual_balance": actual_balance,
                    "difference": difference,
                }
            )
        return result

    def _prepare_report_data(self):
        self.ensure_one()
        self._validate_report_options()
        orders = self.env["pos.order"].with_company(self.company_id).search(
            self._get_order_domain(), order="date_order, id"
        )
        sessions = self.env["pos.session"].with_company(self.company_id).search(
            self._get_session_domain(), order="start_at, id"
        )
        return {
            "company": self.company_id,
            "currency": self.company_id.currency_id,
            "pos_names": ", ".join(self.pos_config_ids.mapped("display_name")),
            "date_from_display": self._format_report_datetime(self.date_from),
            "date_to_display": self._format_report_datetime(self.date_to),
            "timezone_name": self.env.context.get("tz") or self.env.user.tz or "UTC",
            "sessions": self._prepare_session_lines(sessions),
            "sales": self._prepare_sales_summary(orders),
            "payments": self._prepare_payment_summary(orders),
            "product_ranking": self.env[
                "report.point_of_sale.report_saledetails"
            ]._prepare_product_ranking(
                orders,
                self.company_id.currency_id,
                convert_amount=self._order_amount_to_company_currency,
            ),
            "has_orders": bool(orders),
        }

    def _get_report_filename(self):
        self.ensure_one()
        date_from_local = fields.Datetime.context_timestamp(self, self.date_from)
        date_to_local = fields.Datetime.context_timestamp(self, self.date_to)
        return "POS_Shift_%s_%s" % (
            date_from_local.strftime("%Y%m%d_%H%M%S"),
            date_to_local.strftime("%Y%m%d_%H%M%S"),
        )

    def action_print_report(self):
        self.ensure_one()
        self._validate_report_options()
        return self.env.ref(
            "pos_shift_summary_report.action_pos_shift_summary_report_pdf"
        ).report_action(self, data={"wizard_id": self.id}, config=False)

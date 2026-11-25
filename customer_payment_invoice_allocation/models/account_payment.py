# -*- coding: utf-8 -*-
from datetime import date as pydate

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class AccountPayment(models.Model):
    _inherit = "account.payment"

    invoice_allocation_ids = fields.One2many(
        "account.payment.invoice.allocation",
        "payment_id",
        string="Invoice Allocations",
        copy=False,
    )

    allocated_amount = fields.Monetary(
        string="Allocated Amount",
        compute="_compute_allocated_amount",
        currency_field="currency_id",
    )

    unallocated_amount = fields.Monetary(
        string="Unallocated Amount",
        compute="_compute_unallocated_amount",
        currency_field="currency_id",
    )

    @api.depends("invoice_allocation_ids.allocate_amount")
    def _compute_allocated_amount(self):
        for rec in self:
            rec.allocated_amount = sum(rec.invoice_allocation_ids.mapped("allocate_amount"))

    @api.depends("amount", "invoice_allocation_ids.allocate_amount")
    def _compute_unallocated_amount(self):
        for rec in self:
            rec.unallocated_amount = rec.amount - sum(rec.invoice_allocation_ids.mapped("allocate_amount"))

    def _is_customer_inbound_draft(self):
        self.ensure_one()
        return (
            self.state == "draft"
            and self.partner_id
            and self.partner_type == "customer"
            and self.payment_type == "inbound"
        )

    def _get_open_customer_invoices(self):
        self.ensure_one()
        aml_domain = [
            ("partner_id", "=", self.partner_id.id),
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("reconciled", "=", False),
            ("move_id.move_type", "=", "out_invoice"),
            ("move_id.state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
        ]
        open_lines = self.env["account.move.line"].search(
            aml_domain,
            order="date_maturity asc, date asc, id asc",
        )
        return open_lines.mapped("move_id")

    def _prepare_invoice_allocation_vals(self, invoice):
        self.ensure_one()
        receivable_line = invoice.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == "asset_receivable"
                and l.partner_id == invoice.partner_id
                and not l.reconciled
                and not float_is_zero(
                    abs(l.amount_residual),
                    precision_rounding=l.company_currency_id.rounding,
                )
            )
        )[:1]
        if not receivable_line:
            return False

        residual = (
            abs(receivable_line.amount_residual_currency)
            if receivable_line.currency_id
            else abs(receivable_line.amount_residual)
        )

        return {
            "selected": False,
            "invoice_id": invoice.id,
            "currency_id": invoice.currency_id.id,
            "invoice_date": invoice.invoice_date,
            "due_date": invoice.invoice_date_due,
            "invoice_total": invoice.amount_total,
            "residual_amount": residual,
            "allocate_amount": 0.0,
        }

    def _build_invoice_allocation_commands(self):
        self.ensure_one()
        commands = [(5, 0, 0)]
        seen = set()

        for invoice in self._get_open_customer_invoices():
            if invoice.id in seen:
                continue
            seen.add(invoice.id)

            vals = self._prepare_invoice_allocation_vals(invoice)
            if not vals:
                continue
            if float_is_zero(vals["residual_amount"], precision_rounding=invoice.currency_id.rounding or 0.01):
                continue
            commands.append((0, 0, vals))
        return commands

    def _reload_invoice_allocations(self):
        for rec in self:
            if rec._is_customer_inbound_draft():
                rec.invoice_allocation_ids = rec._build_invoice_allocation_commands()
            else:
                rec.invoice_allocation_ids = [(5, 0, 0)]

    @api.onchange("partner_id", "partner_type", "payment_type", "company_id")
    def _onchange_partner_load_open_invoices(self):
        for rec in self:
            rec._reload_invoice_allocations()

    def _sanitize_allocation_commands(self, vals):
        commands = vals.get("invoice_allocation_ids")
        if not commands:
            return vals

        cleaned = []
        for command in commands:
            if not isinstance(command, (list, tuple)) or not command:
                continue

            cmd = command[0]
            if cmd == 0:
                data = command[2] if len(command) > 2 and isinstance(command[2], dict) else {}
                if data.get("invoice_id"):
                    cleaned.append(command)
            else:
                cleaned.append(command)

        vals["invoice_allocation_ids"] = cleaned
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._sanitize_allocation_commands(dict(vals)) for vals in vals_list]
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if rec._is_customer_inbound_draft() and not rec.invoice_allocation_ids and "invoice_allocation_ids" not in vals:
                rec._reload_invoice_allocations()
        return records

    def write(self, vals):
        vals = self._sanitize_allocation_commands(dict(vals))
        reload_needed = any(k in vals for k in ("partner_id", "partner_type", "payment_type", "company_id"))
        res = super().write(vals)

        if reload_needed:
            for rec in self:
                if rec._is_customer_inbound_draft():
                    rec._reload_invoice_allocations()
                else:
                    rec.invoice_allocation_ids.unlink()
        else:
            for rec in self:
                if rec._is_customer_inbound_draft() and not rec.invoice_allocation_ids:
                    rec._reload_invoice_allocations()
        return res

    @api.onchange("amount")
    def _onchange_amount_reset_allocations(self):
        for rec in self:
            total_alloc = sum(rec.invoice_allocation_ids.mapped("allocate_amount"))
            if float_compare(total_alloc, rec.amount, precision_rounding=rec.currency_id.rounding or 0.01) > 0:
                for line in rec.invoice_allocation_ids:
                    line.allocate_amount = 0.0
                    line.selected = False
                return {
                    "warning": {
                        "title": _("Warning"),
                        "message": _("Payment amount changed, allocations were cleared. Please allocate again."),
                    }
                }

    def action_refresh_open_invoices(self):
        for rec in self:
            if rec.state != "draft":
                raise ValidationError(_("You can only refresh open invoices in draft state."))
            rec._reload_invoice_allocations()

    def action_select_all_invoices(self):
        for rec in self:
            rec.invoice_allocation_ids.write({"selected": True})

    def action_unselect_all_invoices(self):
        for rec in self:
            rec.invoice_allocation_ids.write({"selected": False, "allocate_amount": 0.0})

    def action_auto_allocate_invoices(self):
        for payment in self:
            if payment.state != "draft":
                raise ValidationError(_("Auto Allocate can only be used in draft state."))
            if payment.partner_type != "customer" or payment.payment_type != "inbound":
                raise ValidationError(_("Auto Allocate is only available for customer inbound payments."))
            if payment.amount <= 0:
                raise ValidationError(_("Payment amount must be greater than zero."))

            remaining = payment.amount
            precision = payment.currency_id.rounding or 0.01

            for line in payment.invoice_allocation_ids:
                line.allocate_amount = 0.0

            candidate_lines = payment.invoice_allocation_ids.filtered(lambda l: l.selected) or payment.invoice_allocation_ids
            candidate_lines = candidate_lines.sorted(
                key=lambda l: (
                    l.due_date or pydate.max,
                    l.invoice_date or pydate.max,
                    l.invoice_id.name or "",
                    l.id,
                )
            )

            for line in candidate_lines:
                if float_is_zero(remaining, precision_rounding=precision):
                    break
                if line.residual_amount <= 0:
                    continue

                alloc = min(remaining, line.residual_amount)
                line.allocate_amount = alloc
                line.selected = True
                remaining -= alloc

    def _validate_invoice_allocations(self):
        for payment in self:
            if payment.partner_type != "customer" or payment.payment_type != "inbound":
                continue

            precision = payment.currency_id.rounding or 0.01
            total_alloc = sum(payment.invoice_allocation_ids.mapped("allocate_amount"))

            if float_compare(total_alloc, payment.amount, precision_rounding=precision) > 0:
                raise ValidationError(
                    _("Allocated amount (%s) cannot be greater than payment amount (%s).")
                    % (total_alloc, payment.amount)
                )

            for line in payment.invoice_allocation_ids.filtered(lambda l: l.invoice_id):
                line_precision = line.currency_id.rounding or 0.01

                if line.allocate_amount < 0:
                    raise ValidationError(_("Allocate amount cannot be negative."))

                if not line.selected and not float_is_zero(line.allocate_amount, precision_rounding=line_precision):
                    raise ValidationError(
                        _("You cannot allocate amount on an unselected invoice: %s")
                        % line.invoice_id.display_name
                    )

                if float_compare(line.allocate_amount, line.residual_amount, precision_rounding=line_precision) > 0:
                    raise ValidationError(
                        _("Allocated amount for invoice %s cannot be greater than residual amount.")
                        % line.invoice_id.display_name
                    )

    def _get_payment_receivable_line(self):
        self.ensure_one()
        lines = self.move_id.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == "asset_receivable"
                and l.partner_id == self.partner_id
                and not l.reconciled
            )
        )
        return lines[:1]

    def _get_invoice_receivable_line(self, invoice):
        self.ensure_one()
        lines = invoice.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == "asset_receivable"
                and l.partner_id == invoice.partner_id
                and not l.reconciled
            )
        )
        return lines[:1]

    def action_post(self):
        self._validate_invoice_allocations()
        res = super().action_post()
        self._reconcile_selected_invoice_allocations()
        return res


    def _get_line_open_amount_in_currency(self, line, currency, date=False):
        self.ensure_one()
        date = date or self.date or fields.Date.context_today(self)
        if line.currency_id:
            return abs(line.amount_residual_currency)
        return abs(
            line.company_currency_id._convert(
                abs(line.amount_residual),
                currency,
                self.company_id,
                date,
            )
        )

    def _reconcile_selected_invoice_allocations(self):
        Partial = self.env["account.partial.reconcile"]

        for payment in self:
            if payment.partner_type != "customer" or payment.payment_type != "inbound":
                continue

            allocation_lines = payment.invoice_allocation_ids.filtered(
                lambda x: x.selected and x.invoice_id and x.allocate_amount > 0
            )

            for alloc in allocation_lines:
                # Always refresh payment line after every allocation because residual changes.
                payment_line = payment._get_payment_receivable_line()
                if not payment_line:
                    raise ValidationError(_("No outstanding receivable line found on payment entry."))

                invoice = alloc.invoice_id
                invoice_line = payment._get_invoice_receivable_line(invoice)
                if not invoice_line:
                    raise ValidationError(
                        _("No open receivable line found for invoice %s.") % invoice.display_name
                    )

                alloc_amount = abs(alloc.allocate_amount or 0.0)
                alloc_precision = alloc.currency_id.rounding or 0.01
                if float_is_zero(alloc_amount, precision_rounding=alloc_precision):
                    continue

                # Open amounts in allocation currency
                payment_open_alloc = payment._get_line_open_amount_in_currency(
                    payment_line, alloc.currency_id, payment.date
                )
                invoice_open_alloc = payment._get_line_open_amount_in_currency(
                    invoice_line, alloc.currency_id, payment.date
                )

                if float_compare(
                    alloc_amount,
                    payment_open_alloc,
                    precision_rounding=alloc_precision,
                ) > 0:
                    raise ValidationError(
                        _("Allocated amount exceeds open payment balance for invoice %s.")
                        % invoice.display_name
                    )

                if float_compare(
                    alloc_amount,
                    invoice_open_alloc,
                    precision_rounding=alloc_precision,
                ) > 0:
                    raise ValidationError(
                        _("Allocated amount exceeds open residual of invoice %s.")
                        % invoice.display_name
                    )

                min_open_alloc = min(payment_open_alloc, invoice_open_alloc)

                # Best path: let Odoo reconcile natively when allocated amount matches the available amount.
                # This gives the correct widget / payment status and avoids zero-paid artifacts.
                if float_is_zero(
                    alloc_amount - min_open_alloc,
                    precision_rounding=alloc_precision,
                ):
                    (invoice_line + payment_line).reconcile()
                    continue

                company = payment.company_id
                alloc_company_amount = alloc.currency_id._convert(
                    alloc_amount,
                    company.currency_id,
                    company,
                    payment.date or fields.Date.context_today(payment),
                )

                payment_open_company = abs(payment_line.amount_residual)
                invoice_open_company = abs(invoice_line.amount_residual)

                if float_compare(
                    alloc_company_amount,
                    payment_open_company,
                    precision_rounding=company.currency_id.rounding,
                ) > 0:
                    raise ValidationError(
                        _("Not enough open balance left on payment to allocate %s.") % alloc_amount
                    )

                if float_compare(
                    alloc_company_amount,
                    invoice_open_company,
                    precision_rounding=company.currency_id.rounding,
                ) > 0:
                    raise ValidationError(
                        _("Allocated amount exceeds open residual of invoice %s.")
                        % invoice.display_name
                    )

                if invoice_line.balance >= 0 and payment_line.balance <= 0:
                    debit_line = invoice_line
                    credit_line = payment_line
                elif payment_line.balance >= 0 and invoice_line.balance <= 0:
                    debit_line = payment_line
                    credit_line = invoice_line
                else:
                    raise ValidationError(
                        _("Unable to determine reconciliation direction for invoice %s.")
                        % invoice.display_name
                    )

                vals = {
                    "debit_move_id": debit_line.id,
                    "credit_move_id": credit_line.id,
                    "amount": abs(alloc_company_amount),
                    "debit_amount_currency": 0.0,
                    "credit_amount_currency": 0.0,
                }

                # Always populate amount_currency when the move line itself carries a currency.
                # This keeps the invoice payment widget correct and prevents 0.00 paid lines.
                if debit_line.currency_id:
                    if debit_line.currency_id == alloc.currency_id:
                        vals["debit_amount_currency"] = abs(alloc_amount)
                    else:
                        vals["debit_amount_currency"] = debit_line.company_currency_id._convert(
                            abs(alloc_company_amount),
                            debit_line.currency_id,
                            company,
                            payment.date or fields.Date.context_today(payment),
                        )

                if credit_line.currency_id:
                    if credit_line.currency_id == alloc.currency_id:
                        vals["credit_amount_currency"] = abs(alloc_amount)
                    else:
                        vals["credit_amount_currency"] = credit_line.company_currency_id._convert(
                            abs(alloc_company_amount),
                            credit_line.currency_id,
                            company,
                            payment.date or fields.Date.context_today(payment),
                        )

                Partial.create(vals)


class AccountPaymentInvoiceAllocation(models.Model):
    _name = "account.payment.invoice.allocation"
    _description = "Customer Payment Invoice Allocation"
    _order = "due_date, invoice_date, id"

    payment_id = fields.Many2one(
        "account.payment",
        string="Payment",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="payment_id.company_id",
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related="payment_id.partner_id",
        store=True,
        readonly=True,
    )

    selected = fields.Boolean(string="Select")

    invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
        required=True,
        domain=[("move_type", "=", "out_invoice"), ("state", "=", "posted")],
    )
    currency_id = fields.Many2one("res.currency", string="Currency", required=True)
    invoice_date = fields.Date(string="Invoice Date")
    due_date = fields.Date(string="Due Date")
    invoice_total = fields.Monetary(string="Invoice Total", currency_field="currency_id")
    residual_amount = fields.Monetary(string="Residual", currency_field="currency_id")
    allocate_amount = fields.Monetary(string="Allocate Amount", currency_field="currency_id")

    @api.onchange("selected")
    def _onchange_selected(self):
        for rec in self:
            if not rec.selected:
                rec.allocate_amount = 0.0

    @api.onchange("invoice_id")
    def _onchange_invoice_id(self):
        for rec in self:
            if not rec.invoice_id:
                continue

            receivable_line = rec.invoice_id.line_ids.filtered(
                lambda l: (
                    l.account_id.account_type == "asset_receivable"
                    and l.partner_id == rec.invoice_id.partner_id
                    and not l.reconciled
                    and not float_is_zero(
                        abs(l.amount_residual),
                        precision_rounding=l.company_currency_id.rounding,
                    )
                )
            )[:1]

            rec.currency_id = rec.invoice_id.currency_id.id
            rec.invoice_date = rec.invoice_id.invoice_date
            rec.due_date = rec.invoice_id.invoice_date_due
            rec.invoice_total = rec.invoice_id.amount_total
            rec.residual_amount = (
                abs(receivable_line.amount_residual_currency)
                if receivable_line and receivable_line.currency_id
                else abs(receivable_line.amount_residual)
                if receivable_line
                else 0.0
            )

    @api.onchange("allocate_amount")
    def _onchange_allocate_amount(self):
        for rec in self:
            if rec.allocate_amount and not rec.selected:
                rec.selected = True

            if rec.allocate_amount < 0:
                rec.allocate_amount = 0.0
                return {
                    "warning": {
                        "title": _("Warning"),
                        "message": _("Allocate amount cannot be negative."),
                    }
                }

            if rec.allocate_amount > rec.residual_amount:
                rec.allocate_amount = rec.residual_amount
                return {
                    "warning": {
                        "title": _("Warning"),
                        "message": _("Allocate amount cannot exceed residual amount."),
                    }
                }

    @api.constrains("invoice_id", "allocate_amount", "residual_amount")
    def _check_allocate_amount(self):
        for rec in self:
            if not rec.invoice_id:
                continue

            precision = rec.currency_id.rounding or 0.01

            if rec.allocate_amount < 0:
                raise ValidationError(_("Allocate amount cannot be negative."))

            if float_compare(rec.allocate_amount, rec.residual_amount, precision_rounding=precision) > 0:
                raise ValidationError(_("Allocate amount cannot exceed invoice residual."))

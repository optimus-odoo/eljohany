
from odoo import models,fields,api,_
from odoo.exceptions import ValidationError
from datetime import date
import calendar

from datetime import date
from datetime import timedelta
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _get_delivery_blocking_invoices(self):
        """Return active customer invoices that are not posted and settled."""
        self.ensure_one()
        if not self.sale_id:
            return self.env['account.move']
        customer_invoices = self.sale_id.invoice_ids.filtered(
            lambda inv: inv.move_type == 'out_invoice' and inv.state != 'cancel'
        )
        return customer_invoices.filtered(
            lambda inv: (
                inv.state != 'posted'
            )
        )

    def button_validate(self):
        for picking in self:
            blocking_invoices = picking._get_delivery_blocking_invoices()
            if blocking_invoices:
                raise ValidationError(
                    _("لا يمكن اعتماد التحويل لأن أمر البيع مرتبط بفاتورة لم يتم ترحيلها بعد أو سدادها.")
                )
        return super().button_validate()
        
class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def unlink(self):
        for line in self:
            move = line.move_id

            if move.move_type == 'out_invoice' and move.state != 'draft':
                # لازم يكون المستخدم ضمن المجموعة
                if not self.env.user.has_group('acccount.group_delete_customer_invoice_line'):
                    raise ValidationError(_("غير مسموح بمسح اي بند من البنود يرجى التواصل مع مسؤول النظام"))

        return super().unlink()
        
class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_cash_customer = fields.Boolean(
        string="Cash Customer",
        help="Invoices for this customer must be paid before confirmation"
    )
    
class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    def _limit_date_next_month_5(self, ref_date):
        """Return 5th of next month based on reference date"""
        if ref_date.month == 12:
            return date(ref_date.year + 1, 1, 5)
        return date(ref_date.year, ref_date.month + 1, 5)

    def action_post(self):
        today = fields.Date.context_today(self)

        for payment in self:

            # =========================
            # Customer Payments
            # =========================
            today = fields.Date.context_today(self)
            allowed_from = today - timedelta(days=10)
            
            if payment.partner_type == 'customer':
                invoices = payment.reconciled_invoice_ids or payment.line_ids.mapped('move_id').filtered(
                    lambda m: m.move_type in ("out_invoice", "out_refund")
                )
            
                if invoices:
                    invoice_date = invoices[0].invoice_date
            
                    if payment.date != invoice_date:
                        raise ValidationError(
                            "يجب أن يكون تاريخ الدفع مطابقًا لتاريخ الفاتورة."
                        )
            # =========================
            # Vendor Payments
            # =========================
            if payment.partner_type == 'supplier' and payment.date:

                # نستخدم تاريخ اليوم كمرجع لحساب يوم 5
                limit_date = self._limit_date_next_month_5(today)

                if payment.date > limit_date:
                    raise ValidationError(
                        "دفعات الموردين يجب أن تكون قبل أو في يوم 5 من الشهر التالي فقط."
                    )

        return super().action_post()


# class AccountPaymentRegister(models.TransientModel):
#     _inherit = "account.payment.register"
    
#     def _create_payments(self):
#         # invoices المرتبطة بالويزرد
#         moves = self.line_ids.move_id

#         # لو أي فاتورة عميل نقدي ولسه Draft -> امنع العملية أو خلها تسجل بدون ترحيل حسب سياستك
#         cash_draft_moves = moves.filtered(lambda m: m.move_type == 'out_invoice'
#                                                      and m.partner_id.is_cash_customer
#                                                      and m.state == 'draft')
#         if cash_draft_moves:
#             raise UserError("لا يمكن تسجيل دفعة لفاتورة عميل نقدي قبل ترحيلها عبر الإجراء المخصص.")

#         return super()._create_payments()
            
#     def action_create_payments(self):
#         # (اختياري) قبل الدفع: لو الفاتورة draft و Cash -> رحّلها أولاً عشان Odoo يقدر يسجل الدفع عليها
#         moves = self.line_ids.move_id
#         cash_drafts = moves.filtered(lambda m: m.move_type == 'out_invoice'
#                                                and m.partner_id.is_cash_customer
#                                                and m.state == 'draft')
#         if cash_drafts:
#             cash_drafts.action_post()

#         return super().action_create_payments()
        
class AccountMove(models.Model):
    _inherit = 'account.move'
    
    is_cash_customer = fields.Boolean(related='partner_id.is_cash_customer', store=True)
    
    @api.depends('date', 'auto_post', 'is_cash_customer')
    def _compute_hide_post_button(self):
        for record in self:
            record.hide_post_button = ((record.move_type == 'out_invoice' and record.partner_id.is_cash_customer) or record.state != 'draft' or (record.auto_post != 'no' and record.date and record.date > fields.Date.context_today(record)))
        
    def action_register_payment(self):
        res = super().action_register_payment()
        for move in self:
            if (
                move.move_type == 'out_invoice'
                and move.partner_id.is_cash_customer
                and move.state == 'draft'
            ):
                move.action_post()
        return res
    
    def _get_limit_date_from_po(self, po_date):
        if po_date.month == 12:
            return date(po_date.year + 1, 1, 5)
        return date(po_date.year, po_date.month + 1, 5)
        
    def _schedule_backdate_review_activity(self):
        """Create a TODO activity for accounting review."""
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=20,
            summary=_('مراجعة مطلوبة'),
            note=_('فضلاً مراجعة القيد/الفاتورة وإعادة التعيين لمسودة.'),
            date_deadline=fields.Date.context_today(self),
        )

    def _check_backdate_draft_restriction(self, move_date, today, user_can_override):
        if user_can_override or not move_date:
            return
    
        previous_month = today.replace(day=1) - relativedelta(months=1)
    
        if move_date.year == previous_month.year and move_date.month == previous_month.month:
            if today.day > 5:
                raise ValidationError(
                    _("غير مسموح تعديل فواتير أو قيود بتاريخ الشهر السابق بعد يوم 5 من الشهر الحالي.")
                )
        elif move_date < previous_month:
            raise ValidationError(
                _("غير مسموح تعديل فواتير أو قيود بتاريخ أقدم من الشهر السابق.")
            )
            
    def write(self, vals):
        today = fields.Date.context_today(self)

        if 'date' in vals or 'invoice_date' in vals or 'state' in vals:
            for move in self:
                user_can_override = self.env.user.has_group('purchase.group_allow_backdate_invoice')
                if move.move_type in ('out_invoice', 'in_invoice', 'entry'):
                    move_date = vals.get('invoice_date') or vals.get('date') or move.invoice_date or move.date
                    if not move_date:
                        continue
                    if isinstance(move_date, str):
                        move_date = fields.Date.from_string(move_date)
                    previous_month = today.replace(day=1) - relativedelta(months=1)
                    if move_date.year == previous_month.year and move_date.month == previous_month.month:
                        if today.day > 5 and not user_can_override:
                            raise ValidationError(
                                "غير مسموح بتعديل فواتير او قيود بتاريخ الشهر السابق بعد يوم 5 من الشهر الحالي."
                            )
                    elif move_date < previous_month and not user_can_override:
                        raise ValidationError(
                            "غير مسموح بتعديل فواتير او قيود بتاريخ أقدم من الشهر السابق."
                        )
        return super().write(vals)
        
    def action_draft(self):
        today = fields.Date.context_today(self)
        for move in self:
            
            user_can_override = self.env.user.has_group('purchase.group_allow_backdate_invoice')
            if move.move_type == "out_invoice":
                raise UserError(_(
                    "You cannot reset a posted customer invoice to draft.\n"
                    "Please create a Credit Note instead."
                ))

            if move.move_type in ('out_invoice', 'in_invoice', 'entry'):
    
                move_date = move.invoice_date or move.date
                if not move_date:
                    continue
    
                # الشهر السابق فقط
                previous_month = today.replace(day=1) - relativedelta(months=1)
    
                # إذا كان التاريخ من الشهر السابق
                if move_date.year == previous_month.year and move_date.month == previous_month.month:
                    if today.day > 5 and not user_can_override:
                        raise ValidationError(
                            "غير مسموح بتعديل فواتير او قيود بتاريخ الشهر السابق بعد يوم 5 من الشهر الحالي."
                        )
    
                # إذا كان أقدم من الشهر السابق (مثل 31/12/2025 ونحن في فبراير)
                elif move_date < previous_month and not user_can_override:
                    raise ValidationError(
                        "غير مسموح بتعديل فواتير او قيود بتاريخ أقدم من الشهر السابق."
                    )
    
        return super().action_draft()
        
    def action_post(self):
    
        today = fields.Date.context_today(self)
    
        for move in self:
            

            user_can_override = self.env.user.has_group('purchase.group_allow_backdate_invoice')
    
            if move.move_type in ('out_invoice', 'in_invoice', 'entry'):
    
                move_date = move.invoice_date or move.date
                if not move_date:
                    continue
    
                # الشهر السابق فقط
                previous_month = today.replace(day=1) - relativedelta(months=1)
    
                # إذا كان التاريخ من الشهر السابق
                if move_date.year == previous_month.year and move_date.month == previous_month.month:
                    if today.day > 5 and not user_can_override:
                        raise ValidationError(
                            "غير مسموح بتسجيل فواتير او قيود بتاريخ الشهر السابق بعد يوم 5 من الشهر الحالي."
                        )
    
                # إذا كان أقدم من الشهر السابق (مثل 31/12/2025 ونحن في فبراير)
                elif move_date < previous_month and not user_can_override:
                    raise ValidationError(
                        "غير مسموح بتسجيل فواتير او قيود بتاريخ أقدم من الشهر السابق."
                    )
                    

            # Vendor Payments (PO rule)
            if move.move_type == 'outbound' and move.date:
                invoices = move.line_ids.mapped('matched_debit_ids.move_id') |                            move.line_ids.mapped('matched_credit_ids.move_id')
                invoices = invoices.filtered(lambda m: m.move_type == 'in_invoice')

                po_dates = []
                for inv in invoices:
                    pos = inv.invoice_line_ids.mapped('purchase_line_id.order_id')
                    po_dates += pos.mapped('date_order')

                if po_dates:
                    po_date = min(po_dates).date()
                    limit_date = self._get_limit_date_from_po(po_date)
                    if move.date > limit_date:
                        raise ValidationError(
                            "لا يمكن ترحيل السداد بعد يوم 5 من الشهر التالي لتاريخ أمر الشراء."
                        )

            # Customer Invoices 

            if move.move_type in ('out_invoice', 'out_refund'):
                if move.invoice_date != today and not self.env.user.has_group('account.register_any_invoice'):
                    raise ValidationError(
                        "تاريخ فاتورة العميل او الاشعار الدائن يجب أن يكون تاريخ اليوم فقط."
                    )

            for move in self.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted'):
                sale_orders = move.invoice_line_ids.mapped('sale_line_ids.order_id')
                for sale in sale_orders:
                    for picking in sale.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
                        if picking.state == 'draft':
                            picking.action_confirm()
    
                        if picking.state in ('confirmed', 'waiting'):
                            picking.action_assign()
    
                        for ml in picking.move_line_ids_without_package:
                            qty = getattr(ml, 'reserved_uom_qty', 0.0) or getattr(ml, 'product_uom_qty', 0.0)
                            if not ml.qty_done:
                                ml.qty_done = qty
    
                        # لو فيه wizard يرجع أكشن، نتجاهله
                        try:
                            picking.button_validate()
                        except Exception:
                            pass

            if move.move_type == 'inbound':
                if move.date != today and not self.env.user.has_group('account.register_any_invoice'):
                    raise ValidationError(
                        "تاريخ سداد العميل يجب أن يكون تاريخ اليوم فقط."
                    )

        return super().action_post()

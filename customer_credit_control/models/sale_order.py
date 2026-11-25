# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        today = fields.Date.context_today(self)

        for order in self:
            if not self.env.user.has_group('account.group_allow_user_exceed'):
                partner = order.partner_id
    
                # شرط 1: حالة المتابعة (فواتير متأخرة)
                status = getattr(partner, "followup_status", False) or getattr(partner, "followup_state", False)
                if partner.followup_status == "with_overdue_invoices":
                    raise UserError(_(
                        "لا يمكن تأكيد أمر البيع لأن على العميل فواتير متأخرة (Overdue Invoices).\n\n"
                        "العميل: %s"
                    ) % (partner.display_name))
    
                # شرط 2: تجاوز الحد الائتماني (إذا كان محدد)
                if partner.x_credit_limit and partner.x_credit_limit > 0:
                    company = order.company_id
                    company_currency = company.currency_id
    
                    current_due = partner.credit or 0.0  # بعملة الشركة
    
                    so_total_company_cur = order.currency_id._convert(
                        order.amount_total,
                        company_currency,
                        company,
                        order.date_order or today,
                    )
    
                    projected_due = current_due + so_total_company_cur
    
                    if projected_due > partner.x_credit_limit:
                        raise UserError(_(
                            "لا يمكن تأكيد أمر البيع لأن العميل تجاوز الحد الائتماني.\n\n"
                            "العميل: %s\n"
                            "الرصيد الحالي المستحق: %s %s\n"
                            "قيمة الطلب (بعملة الشركة): %s %s\n"
                            "الرصيد المتوقع بعد التأكيد: %s %s\n"
                            "الحد الائتماني: %s %s"
                        ) % (
                            partner.display_name,
                            company_currency.round(current_due), company_currency.name,
                            company_currency.round(so_total_company_cur), company_currency.name,
                            company_currency.round(projected_due), company_currency.name,
                            company_currency.round(partner.x_credit_limit), company_currency.name,
                        ))

        return super().action_confirm()
